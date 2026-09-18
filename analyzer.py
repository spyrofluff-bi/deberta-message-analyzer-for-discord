"""
DeBERTa-v3 Model Inference Engine for Discord Message Analysis.
Supports Hugging Face zero-shot classification pipelines, asynchronous execution,
probability scale calculation, and intelligent fallback handling.
"""

import time
import logging
import asyncio
from typing import Dict, Any, List, Optional
from config import MODEL_NAME, DEFAULT_LABELS, PRIMARY_EVIL_LABEL

logger = logging.getLogger("bot.analyzer")

class DebertaAnalyzer:
    _instance: Optional["DebertaAnalyzer"] = None

    def __init__(self):
        self.model_name = MODEL_NAME
        self.pipeline = None
        self.device = "cpu"
        self.status = "unloaded"  # unloaded, loading, ready, fallback
        self.error_message: Optional[str] = None
        self.load_duration_sec: float = 0.0
        self.total_evaluations: int = 0
        self.total_inference_time_ms: float = 0.0

    @classmethod
    def get_instance(cls) -> "DebertaAnalyzer":
        if cls._instance is None:
            cls._instance = DebertaAnalyzer()
        return cls._instance

    def load_model_sync(self):
        """Loads the DeBERTa-v3 pipeline synchronously."""
        self.status = "loading"
        start_t = time.perf_counter()
        logger.info(f"Loading DeBERTa-v3 model: {self.model_name}...")
        try:
            import torch
            from transformers import pipeline

            # Detect CUDA or CPU
            if torch.cuda.is_available():
                self.device = "cuda:0"
                pipeline_device = 0
            else:
                self.device = "cpu"
                pipeline_device = -1

            self.pipeline = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                device=pipeline_device
            )
            self.status = "ready"
            self.load_duration_sec = round(time.perf_counter() - start_t, 2)
            logger.info(f"DeBERTa-v3 loaded successfully in {self.load_duration_sec}s on {self.device}!")
        except Exception as e:
            logger.warning(f"Could not load DeBERTa-v3 pipeline ({e}). Falling back to heuristic/simulation analyzer until loaded.")
            self.status = "fallback"
            self.error_message = str(e)
            self.pipeline = None

    async def initialize(self):
        """Asynchronously triggers model loading in background worker."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.load_model_sync)

    def _fallback_evaluate(self, text: str, candidate_labels: List[str], evil_label: str) -> Dict[str, Any]:
        """
        Lightweight fallback scorer used if the heavy DeBERTa weights
        are downloading or offline. Analyzes toxicity/hostility markers.
        """
        text_lower = text.lower()
        evil_keywords = [
            "kill", "hate", "die", "attack", "destroy", "idiot", "scam",
            "threat", "murder", "toxic", "evil", "steal", "hack", "bomb",
            "abuse", "harass", "dox", "raid", "trash", "loser", "stupid"
        ]
        mild_keywords = ["bad", "annoying", "shut up", "ugly", "fake"]

        score = 0.05  # baseline benign probability
        for kw in evil_keywords:
            if kw in text_lower:
                score += 0.35
        for kw in mild_keywords:
            if kw in text_lower:
                score += 0.15

        # Check for ALL CAPS yelling
        if len(text) > 6 and text.isupper():
            score += 0.15

        # Clamp between 0.02 and 0.99
        evil_prob = round(max(0.02, min(0.99, score)), 4)
        safe_prob = round(1.0 - evil_prob, 4)

        scores_dict = {
            evil_label: evil_prob,
            "safe and benign casual conversation": safe_prob
        }
        top_label = evil_label if evil_prob > safe_prob else "safe and benign casual conversation"
        top_score = max(evil_prob, safe_prob)

        return {
            "evil_probability": evil_prob,
            "top_label": top_label,
            "top_score": top_score,
            "scores": scores_dict,
            "model_used": f"{self.model_name} (Fallback Mode)"
        }

    def evaluate_sync(self, text: str, candidate_labels: Optional[List[str]] = None, evil_label: Optional[str] = None) -> Dict[str, Any]:
        """Synchronously runs inference on a text string."""
        start_t = time.perf_counter()
        labels = candidate_labels or DEFAULT_LABELS
        primary_evil = evil_label or PRIMARY_EVIL_LABEL

        # If primary_evil not in labels, add it
        if primary_evil not in labels:
            labels = [primary_evil] + [l for l in labels if l != primary_evil]

        if not text or not text.strip():
            return {
                "evil_probability": 0.0,
                "top_label": "safe and benign casual conversation",
                "top_score": 1.0,
                "scores": {lbl: (0.0 if lbl == primary_evil else 1.0) for lbl in labels},
                "latency_ms": 0.1,
                "model_used": self.model_name
            }

        if self.status == "ready" and self.pipeline is not None:
            try:
                # Run zero-shot classification with hypothesis template
                hypothesis_template = "This message is {}."
                res = self.pipeline(
                    text,
                    candidate_labels=labels,
                    hypothesis_template=hypothesis_template,
                    multi_label=False
                )
                raw_labels = res["labels"]
                raw_scores = res["scores"]
                scores_dict = {lbl: round(float(scr), 4) for lbl, scr in zip(raw_labels, raw_scores)}

                # Evil probability is the score for the primary evil label
                evil_prob = scores_dict.get(primary_evil, 0.0)
                top_label = raw_labels[0]
                top_score = round(float(raw_scores[0]), 4)
                model_used = self.model_name
            except Exception as e:
                logger.error(f"Inference error with pipeline: {e}. Using fallback.")
                fb_res = self._fallback_evaluate(text, labels, primary_evil)
                scores_dict = fb_res["scores"]
                evil_prob = fb_res["evil_probability"]
                top_label = fb_res["top_label"]
                top_score = fb_res["top_score"]
                model_used = fb_res["model_used"]
        else:
            fb_res = self._fallback_evaluate(text, labels, primary_evil)
            scores_dict = fb_res["scores"]
            evil_prob = fb_res["evil_probability"]
            top_label = fb_res["top_label"]
            top_score = fb_res["top_score"]
            model_used = fb_res["model_used"]

        latency_ms = round((time.perf_counter() - start_t) * 1000, 1)

        # Update metrics
        self.total_evaluations += 1
        self.total_inference_time_ms += latency_ms

        return {
            "evil_probability": evil_prob,
            "top_label": top_label,
            "top_score": top_score,
            "scores": scores_dict,
            "latency_ms": latency_ms,
            "model_used": model_used
        }

    async def evaluate_async(self, text: str, candidate_labels: Optional[List[str]] = None, evil_label: Optional[str] = None) -> Dict[str, Any]:
        """Asynchronously executes inference in executor thread to prevent blocking gateway heartbeats."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.evaluate_sync, text, candidate_labels, evil_label)

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns model health and diagnostic status."""
        avg_lat = round((self.total_inference_time_ms / self.total_evaluations), 1) if self.total_evaluations > 0 else 0.0
        return {
            "model_name": self.model_name,
            "status": self.status,
            "device": self.device,
            "load_duration_sec": self.load_duration_sec,
            "total_evaluations": self.total_evaluations,
            "avg_latency_ms": avg_lat,
            "error_message": self.error_message
        }
