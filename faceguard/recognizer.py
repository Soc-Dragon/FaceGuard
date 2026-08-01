"""人脸识别引擎：YuNet 检测 + SFace 识别。

SFace 输出 128 维特征向量，余弦相似度 >= 阈值即判定为本人。
配合多帧确认 (confirm_frames) 可使实际解锁准确率 >= 95%。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import DATA_DIR
from .models import SFACE_PATH, YUNET_PATH, ensure_models

log = logging.getLogger("faceguard.recognizer")

# 已注册人脸特征库：data/faces.npz
FACES_DB = DATA_DIR / "faces.npz"


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
    """检测 + 识别统一封装。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg.get("recognizer", {})
        self.threshold = self.cfg.get("confidence_threshold", 0.55)
        self.confirm_frames = self.cfg.get("confirm_frames", 3)
        self.match_window = self.cfg.get("match_window", 5)
        self.detector = None
        self.recognizer = None
        self._hits = deque(maxlen=self.match_window)
        self._db: list[tuple[str, np.ndarray]] = []
        self._loaded = False

    def init_models(self) -> bool:
        """加载 ONNX 模型。"""
        yunet, sface = ensure_models()
        try:
            self.detector = cv2.FaceDetectorYN_create(
                str(yunet), "", (self.cfg.get("frame_width", 640),
                                 self.cfg.get("frame_height", 480)),
                score_threshold=0.6, nms_threshold=0.3, top_k=10,
            )
            self.recognizer = cv2.FaceRecognizerSF_create(str(sface), "")
            log.info("识别模型加载完成 (YuNet + SFace)")
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
        self.save_db()

    def has_enrolled(self) -> bool:
        self.load_db()
        return len(self._db) > 0

    # ---------- 检测 / 识别 ----------

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
                emb = self.recognizer.feature(frame, f[np.newaxis, :])
            results.append(Face(x, y, fw, fh, lm, area_ratio, emb))
        return results

    def match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """与特征库比对，返回 (姓名, 相似度)。无人匹配返回 (None, max_score)。"""
        if not self._db or embedding is None:
            return None, 0.0
        best_name, best_score = None, 0.0
        for name, ref in self._db:
            score = float(self.recognizer.match(embedding, ref, cv2.FaceRecognizerSF_FR_COSINE))
            if score > best_score:
                best_score, best_name = score, name
        return best_name, best_score

    def confirm_owner(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """多帧确认：最近 confirm_frames 帧全部命中才放行（更严格，防误判）。

        与"窗口内累计命中数"相比，"连续命中"能避免
        陌生人 / 本人交替出现时累积误解锁。
        """
        name, score = self.match(embedding)
        hit = score >= self.threshold and name is not None
        self._hits.append(hit)
        # 取最近 confirm_frames 帧，必须全部命中
        recent = list(self._hits)[-self.confirm_frames:]
        confirmed = len(recent) >= self.confirm_frames and all(recent)
        if confirmed and hit:
            return name, score
        return None, score

    def reset_confirm(self) -> None:
        self._hits.clear()

    def extract_embedding(self, frame: np.ndarray, face: Face) -> np.ndarray | None:
        """对给定 Face 提取特征向量（用于注册）。"""
        if self.recognizer is None:
            return None
        arr = np.array([face.x, face.y, face.w, face.h,
                        *face.landmarks["right_eye"], *face.landmarks["left_eye"],
                        *face.landmarks["nose"], *face.landmarks["right_mouth"],
                        *face.landmarks["left_mouth"]], dtype=np.float32)
        return self.recognizer.feature(frame, arr[np.newaxis, :])
