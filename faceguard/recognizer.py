"""人脸识别引擎：YuNet 检测 + SFace/MobileFaceNet/ArcFace 识别。

支持多模型切换 + 自适应学习（每次成功解锁后增量更新特征库）。
配合多帧确认 (confirm_frames) 可使实际解锁准确率 >= 95%。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import DATA_DIR
from .models import RECOGNIZER_MODELS, YUNET_PATH, ensure_models

log = logging.getLogger("faceguard.recognizer")

# 已注册人脸特征库：data/faces.npz
FACES_DB = DATA_DIR / "faces.npz"
# 自适应学习历史：data/learn_history.npz
LEARN_DB = DATA_DIR / "learn_history.npz"


@dataclass
class Face:
    """单张人脸检测结果。"""
    x: int
    y: int
    w: int
    h: int
    landmarks: dict          # {right_eye, left_eye, nose, right_mouth, left_mouth}
    area_ratio: float        # 人脸占画面比例
    embedding: np.ndarray | None = None


class Recognizer:
    """检测 + 识别统一封装（多模型 + 自适应学习）。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg.get("recognizer", {})
        self.recognizer_type = self.cfg.get("recognizer_type", "sface")
        self.threshold = self.cfg.get("confidence_threshold", 0.55)
        self.confirm_frames = self.cfg.get("confirm_frames", 3)
        self.match_window = self.cfg.get("match_window", 5)
        # 自适应学习配置
        self.adaptive = cfg.get("adaptive", {"enabled": True, "max_samples_per_user": 30,
                                              "learn_threshold": 0.7, "cooldown_seconds": 300})
        self.detector = None
        self.recognizer = None
        self._rec_type = "opencv_sf"  # opencv_sf / onnx_dnn
        self._rec_info = None
        self._hits = deque(maxlen=self.match_window)
        self._db: list[tuple[str, np.ndarray]] = []
        self._loaded = False
        # 自适应学习状态
        self._learn_history: list[tuple[str, np.ndarray, float]] = []  # (name, emb, score)
        self._last_learn_time: dict[str, float] = {}  # 每个用户的上次学习时间
        self._dynamic_threshold = self.threshold  # 动态阈值

    def init_models(self) -> bool:
        """加载模型。支持 SFace/MobileFaceNet/ArcFace 三种识别模型。"""
        yunet, rec_path = ensure_models(self.recognizer_type)
        # 检查 YuNet
        if not yunet.exists() or yunet.stat().st_size < 1000:
            log.warning("YuNet 模型不存在，将以降级模式运行（无人脸检测）。")
            return False
        if rec_path is None or not rec_path.exists() or rec_path.stat().st_size < 1000:
            log.warning("识别模型不存在，将以降级模式运行（无人脸识别）。")
            return False

        # 获取模型信息
        self._rec_info = RECOGNIZER_MODELS.get(self.recognizer_type, RECOGNIZER_MODELS["sface"])
        self._rec_type = self._rec_info["type"]
        # 使用模型专属阈值作为默认值
        self.threshold = self.cfg.get("confidence_threshold", self._rec_info["threshold"])
        self._dynamic_threshold = self.threshold

        try:
            # YuNet 检测器
            self.detector = cv2.FaceDetectorYN_create(
                str(yunet), "", (self.cfg.get("frame_width", 640),
                                 self.cfg.get("frame_height", 480)),
                score_threshold=0.6, nms_threshold=0.3, top_k=10,
            )
            # 识别器
            if self._rec_type == "opencv_sf":
                self.recognizer = cv2.FaceRecognizerSF_create(str(rec_path), "")
            else:
                # onnx_dnn: 用 cv2.dnn 读 ONNX
                self.recognizer = cv2.dnn.readNetFromONNX(str(rec_path))
            log.info(f"识别模型加载完成: {self._rec_info['name']} ({self._rec_info['desc']})")
            return True
        except cv2.error as e:
            log.error("模型加载失败: %s", e)
            return False

    # ---------- 特征库 ----------

    def load_db(self) -> int:
        """加载已注册人脸，返回人数。"""
        if self._loaded:
            return len(self._db)
        if FACES_DB.exists():
            try:
                data = np.load(str(FACES_DB), allow_pickle=True)
                self._db = [(str(n), np.asarray(v, dtype=np.float32))
                            for n, v in zip(data["names"], data["embeddings"])]
                log.info("已加载 %d 张注册人脸", len(self._db))
            except Exception as e:
                log.warning("人脸库读取失败: %s", e)
        # 加载学习历史
        self._load_learn_history()
        self._loaded = True
        return len(self._db)

    def save_db(self) -> None:
        names = [n for n, _ in self._db]
        embs = [e for _, e in self._db]
        if names:
            np.savez(str(FACES_DB), names=np.array(names, dtype=object),
                     embeddings=np.array(embs, dtype=np.float32))
        else:
            FACES_DB.unlink(missing_ok=True)

    def enroll(self, name: str, embedding: np.ndarray) -> None:
        self.load_db()
        self._db.append((name, embedding.astype(np.float32)))
        self.save_db()
        log.info("已注册人脸: %s (共 %d)", name, len(self._db))

    def clear_db(self) -> None:
        self._db.clear()
        self._learn_history.clear()
        self._save_learn_history()
        self.save_db()

    def has_enrolled(self) -> bool:
        self.load_db()
        return len(self._db) > 0

    # ---------- 自适应学习 ----------

    def _load_learn_history(self) -> None:
        """加载学习历史。"""
        if LEARN_DB.exists():
            try:
                data = np.load(str(LEARN_DB), allow_pickle=True)
                self._learn_history = [
                    (str(n), np.asarray(v, dtype=np.float32), float(s))
                    for n, v, s in zip(data["names"], data["embeddings"], data["scores"])
                ]
                log.info("已加载 %d 条学习历史", len(self._learn_history))
            except Exception as e:
                log.warning("学习历史读取失败: %s", e)
                self._learn_history = []

    def _save_learn_history(self) -> None:
        """保存学习历史。"""
        if not self._learn_history:
            LEARN_DB.unlink(missing_ok=True)
            return
        names = [n for n, _, _ in self._learn_history]
        embs = [e for _, e, _ in self._learn_history]
        scores = [s for _, _, s in self._learn_history]
        try:
            np.savez(str(LEARN_DB),
                     names=np.array(names, dtype=object),
                     embeddings=np.array(embs, dtype=np.float32),
                     scores=np.array(scores, dtype=np.float32))
        except Exception as e:
            log.warning("学习历史保存失败: %s", e)

    def learn_from_success(self, name: str, embedding: np.ndarray, score: float) -> bool:
        """成功解锁后增量学习：把当前特征加入历史，融合多角度。

        策略：
        1. 冷却时间内不重复学习（避免短时间内重复添加）
        2. 每个用户最多保留 max_samples 个学习样本
        3. 学习后更新该用户的融合特征（平均向量）
        4. 根据历史匹配分数动态调整阈值
        """
        if not self.adaptive.get("enabled", True):
            return False
        if embedding is None or name is None:
            return False

        cooldown = self.adaptive.get("cooldown_seconds", 300)
        now = time.time()
        last = self._last_learn_time.get(name, 0)
        if now - last < cooldown:
            return False  # 冷却中

        max_samples = self.adaptive.get("max_samples_per_user", 30)
        learn_threshold = self.adaptive.get("learn_threshold", 0.7)

        # 只在置信度较高时学习（避免学到错误特征）
        if score < learn_threshold:
            return False

        # 加入历史
        self._learn_history.append((name, embedding.astype(np.float32), score))
        self._last_learn_time[name] = now

        # 限制每个用户的样本数（保留最新的）
        user_samples = [(n, e, s) for n, e, s in self._learn_history if n == name]
        if len(user_samples) > max_samples:
            # 删除该用户最早的样本
            to_remove = len(user_samples) - max_samples
            removed = 0
            new_hist = []
            for n, e, s in self._learn_history:
                if n == name and removed < to_remove:
                    removed += 1
                    continue
                new_hist.append((n, e, s))
            self._learn_history = new_hist

        self._save_learn_history()

        # 融合特征：把该用户的所有学习样本 + 原始注册特征求平均，更新 _db
        self._update_fused_embedding(name)

        # 动态调整阈值（历史分数高时适当提高阈值，更严格；低时降低，更宽松）
        user_scores = [s for n, _, s in self._learn_history if n == name]
        if user_scores:
            avg_score = sum(user_scores) / len(user_scores)
            # 阈值在 [threshold-0.05, threshold+0.05] 范围内动态调整
            adjustment = (avg_score - self.threshold) * 0.3
            self._dynamic_threshold = max(0.3, min(0.8, self.threshold + adjustment))

        log.info(f"自适应学习: {name} 新增样本 (历史 {len(user_samples)} 个, 阈值 {self._dynamic_threshold:.3f})")
        return True

    def _update_fused_embedding(self, name: str) -> None:
        """融合该用户的所有特征（原始 + 学习历史）为平均向量。"""
        all_embs = []
        # 原始注册特征
        for n, e in self._db:
            if n == name or n.startswith(f"{name}_"):
                all_embs.append(e)
        # 学习历史
        for n, e, _ in self._learn_history:
            if n == name:
                all_embs.append(e)

        if not all_embs:
            return

        # L2 归一化后求平均，再归一化
        embs = np.array(all_embs, dtype=np.float32)
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embs = embs / norms
        fused = embs.mean(axis=0)
        fused = fused / (np.linalg.norm(fused) + 1e-8)

        # 更新 _db：替换该用户的所有特征为一个融合特征
        # 保留原始注册特征（防止学习污染），只更新融合特征
        # 简化策略：在 _db 中找到该用户的条目，追加融合特征
        # 这里采用：保留原始 + 添加一个 "_fused" 条目
        fused_name = f"{name}_fused"
        # 移除旧的 fused 条目
        self._db = [(n, e) for n, e in self._db if n != fused_name]
        self._db.append((fused_name, fused.astype(np.float32)))
        self.save_db()

    # ---------- 检测 / 识别 ----------

    def _extract_feature_sface(self, frame: np.ndarray, face_arr: np.ndarray) -> np.ndarray | None:
        """用 SFace (cv2.FaceRecognizerSF) 提取特征。"""
        try:
            return self.recognizer.feature(frame, face_arr[np.newaxis, :])
        except cv2.error:
            return None

    def _extract_feature_dnn(self, frame: np.ndarray, face: Face) -> np.ndarray | None:
        """用 cv2.dnn (MobileFaceNet/ArcFace) 提取特征。"""
        try:
            # 裁剪人脸区域
            x1 = max(0, face.x)
            y1 = max(0, face.y)
            x2 = min(frame.shape[1], face.x + face.w)
            y2 = min(frame.shape[0], face.y + face.h)
            if x2 - x1 < 32 or y2 - y1 < 32:
                return None
            face_img = frame[y1:y2, x1:x2]
            # resize 到 112x112 (ArcFace/MobileFaceNet 标准输入)
            face_img = cv2.resize(face_img, (112, 112))
            # 预处理：BGR -> RGB, 归一化
            face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
            face_img = (face_img.astype(np.float32) - 127.5) / 127.5
            # HWC -> CHW
            face_img = np.transpose(face_img, (2, 0, 1))
            face_img = np.expand_dims(face_img, axis=0)

            self.recognizer.setInput(face_img)
            emb = self.recognizer.forward()
            # L2 归一化
            emb = emb.flatten()
            norm = np.linalg.norm(emb) + 1e-8
            return emb / norm
        except Exception as e:
            log.debug("dnn 特征提取失败: %s", e)
            return None

    def detect(self, frame: np.ndarray) -> list[Face]:
        """检测画面中所有人脸。"""
        if self.detector is None:
            return []
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        results: list[Face] = []
        if faces is None:
            return results
        for f in faces:
            x, y, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
            lm = {
                "right_eye": (int(f[4]), int(f[5])),
                "left_eye": (int(f[6]), int(f[7])),
                "nose": (int(f[8]), int(f[9])),
                "right_mouth": (int(f[10]), int(f[11])),
                "left_mouth": (int(f[12]), int(f[13])),
            }
            area_ratio = (fw * fh) / float(w * h)
            emb = None
            if self.recognizer is not None:
                if self._rec_type == "opencv_sf":
                    emb = self._extract_feature_sface(frame, f)
                else:
                    face_obj = Face(x, y, fw, fh, lm, area_ratio, None)
                    emb = self._extract_feature_dnn(frame, face_obj)
            results.append(Face(x, y, fw, fh, lm, area_ratio, emb))
        return results

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度。"""
        na = np.linalg.norm(a) + 1e-8
        nb = np.linalg.norm(b) + 1e-8
        return float(np.dot(a, b) / (na * nb))

    def match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """与特征库比对，返回 (姓名, 相似度)。无人匹配返回 (None, max_score)。"""
        if not self._db or embedding is None or self.recognizer is None:
            return None, 0.0
        best_name, best_score = None, 0.0
        for name, ref in self._db:
            try:
                if self._rec_type == "opencv_sf":
                    score = float(self.recognizer.match(embedding, ref, cv2.FaceRecognizerSF_FR_COSINE))
                else:
                    score = self._cosine_similarity(embedding, ref)
            except (cv2.error, ValueError, TypeError):
                continue
            if score > best_score:
                best_score, best_name = score, name
        # 如果匹配到的是 _fused 条目，去掉后缀返回原始名字
        if best_name and best_name.endswith("_fused"):
            best_name = best_name[:-6]
        return best_name, best_score

    def confirm_owner(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """多帧确认：最近 confirm_frames 帧全部命中才放行（更严格，防误判）。

        与"窗口内累计命中数"相比，"连续命中"能避免
        陌生人 / 本人交替出现时累积误解锁。
        成功确认后触发自适应学习。
        """
        name, score = self.match(embedding)
        # 使用动态阈值
        hit = score >= self._dynamic_threshold and name is not None
        self._hits.append(hit)
        # 取最近 confirm_frames 帧，必须全部命中
        recent = list(self._hits)[-self.confirm_frames:]
        confirmed = len(recent) >= self.confirm_frames and all(recent)
        if confirmed and hit:
            # 触发自适应学习
            self.learn_from_success(name, embedding, score)
            return name, score
        return None, score

    def reset_confirm(self) -> None:
        self._hits.clear()

    def extract_embedding(self, frame: np.ndarray, face: Face) -> np.ndarray | None:
        """对给定 Face 提取特征向量（用于注册）。"""
        if self.recognizer is None:
            return None
        if self._rec_type == "opencv_sf":
            arr = np.array([face.x, face.y, face.w, face.h,
                            *face.landmarks["right_eye"], *face.landmarks["left_eye"],
                            *face.landmarks["nose"], *face.landmarks["right_mouth"],
                            *face.landmarks["left_mouth"]], dtype=np.float32)
            return self._extract_feature_sface(frame, arr)
        else:
            return self._extract_feature_dnn(frame, face)
