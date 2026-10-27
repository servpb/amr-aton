"""Screen Perceiver Module for Aton.

Provides on-demand screen and active window capture, Win32 window context detection,
multimodal visual understanding via Gemini Vision, and screen element coordinate mapping.
Operates with strict privacy: only captures when explicitly invoked by user request.
"""

import base64
import ctypes
from ctypes import wintypes
import io
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

from PIL import Image, ImageGrab
import pyautogui

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore

from src.config import settings

logger = logging.getLogger(__name__)

# Configure PyAutoGUI safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


class ScreenPerceiver:
    """Core engine for screen capture, active window inspection, and multimodal vision analysis."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        vision_model: Optional[str] = None,
    ):
        self.gemini_api_key = gemini_api_key or settings.gemini_api_key
        self.vision_model = vision_model or settings.gemini_vision_model
        self._user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        self._client = None
        if genai and self.gemini_api_key:
            try:
                self._client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize google-genai Client: {e}")

    def get_active_window_info(self) -> Dict[str, Any]:
        """Get handle, title, and coordinates of the active foreground window on Windows."""
        if not self._user32:
            return {"title": "Ambiente não-Windows", "rect": (0, 0, 1920, 1080), "width": 1920, "height": 1080}

        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            screen_w, screen_h = pyautogui.size()
            return {"title": "Área de Trabalho", "rect": (0, 0, screen_w, screen_h), "width": screen_w, "height": screen_h}

        # Window Title
        length = self._user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip() or "Janela sem título"

        # Window Rect (left, top, right, bottom)
        rect = wintypes.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        left = max(0, rect.left)
        top = max(0, rect.top)
        right = max(left, rect.right)
        bottom = max(top, rect.bottom)
        width = right - left
        height = bottom - top

        return {
            "hwnd": hwnd,
            "title": title,
            "rect": (left, top, right, bottom),
            "width": width,
            "height": height,
        }

    def capture_screen(self, target: str = "janela_ativa") -> Tuple[Image.Image, Dict[str, Any]]:
        """Capture screen image on demand.
        
        Args:
            target: 'janela_ativa' for the foreground window, or 'fullscreen' for full monitor.

        Returns:
            Tuple of (PIL.Image, window_metadata_dict).
        """
        win_info = self.get_active_window_info()
        w = max(100, win_info.get("width", 1920))
        h = max(100, win_info.get("height", 1080))

        img = None
        if target == "janela_ativa" and win_info.get("width", 0) > 50 and win_info.get("height", 0) > 50:
            bbox = win_info["rect"]
            try:
                img = ImageGrab.grab(bbox=bbox)
            except Exception as e:
                logger.warning(f"Error cropping active window {bbox}: {e}")

        if img is None:
            try:
                img = pyautogui.screenshot()
                win_info["rect"] = (0, 0, img.width, img.height)
                win_info["width"] = img.width
                win_info["height"] = img.height
            except Exception as e:
                logger.warning(f"Screen grab failed (headless or locked desktop): {e}. Using fallback image.")
                img = Image.new("RGB", (w, h), color=(30, 30, 35))
                win_info["rect"] = (0, 0, w, h)
                win_info["width"] = w
                win_info["height"] = h

        return img, win_info

    def optimize_image_for_gemini(self, img: Image.Image, max_dim: int = 1280) -> Tuple[str, float]:
        """Resize image preserving aspect ratio and convert to base64 JPEG.
        
        Returns:
            Tuple of (base64_jpeg_string, scale_factor).
        """
        w, h = img.size
        scale = 1.0
        if max(w, h) > max_dim:
            if w >= h:
                scale = max_dim / float(w)
                new_w = max_dim
                new_h = int(h * scale)
            else:
                scale = max_dim / float(h)
                new_h = max_dim
                new_w = int(w * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Convert to RGB if RGBA
        if img.mode != "RGB":
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64_str, scale

    def analyze_visual_content(
        self,
        prompt: str,
        target: str = "janela_ativa",
    ) -> Dict[str, Any]:
        """Capture screen and query Gemini Multimodal Vision API.

        Returns structured visual description, detected elements, and coordinate mapping.
        """
        if not self.gemini_api_key:
            return {
                "status": "error",
                "message": "Chave GEMINI_API_KEY não configurada para análise visual.",
                "window": self.get_active_window_info(),
            }

        img, win_info = self.capture_screen(target=target)
        b64_image, scale = self.optimize_image_for_gemini(img)

        # Enhanced prompt for Gemini Vision
        system_instructions = (
            "Você é o módulo de percepção visual do assistente Aton. "
            "Analise a imagem da tela fornecida e responda em Português do Brasil com precisão e clareza. "
            "Se o usuário pedir para descrever ou ler, forneça um texto executivo, fluído e natural para ser falado por áudio "
            "(sem markdown excessivo, sem asteriscos, sem tabelas complexas). "
            "Se o usuário pedir para localizar um elemento (botão, campo, link, menu), identifique a caixa delimitadora "
            "(bounding box) do elemento no formato normalizado [ymin, xmin, ymax, xmax] com valores entre 0 e 1000."
        )

        full_prompt = f"{system_instructions}\n\nJanela ativa informada pelo sistema: '{win_info.get('title')}'\n\nSolicitação: {prompt}"

        # Decode JPEG bytes for multimodal SDK input
        raw_jpeg_bytes = base64.b64decode(b64_image)

        # Candidates to try in order (resilient against model migration or high load 503)
        candidate_models = [
            self.vision_model,
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3-flash-preview",
            "gemini-3.5-flash-lite",
        ]
        seen = set()
        unique_models = []
        for m in candidate_models:
            clean_m = m.replace("models/", "")
            if clean_m not in seen:
                seen.add(clean_m)
                unique_models.append(clean_m)

        last_error = None

        # 1. Primary path: Official google-genai SDK
        if self._client and types:
            for model_name in unique_models:
                try:
                    part = types.Part.from_bytes(data=raw_jpeg_bytes, mime_type="image/jpeg")
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=[full_prompt, part],
                    )
                    reply_text = (response.text or "").strip()
                    if reply_text:
                        return {
                            "status": "success",
                            "text": reply_text,
                            "window": win_info,
                            "image_size": (img.width, img.height),
                            "model_used": model_name,
                        }
                except Exception as sdk_err:
                    logger.warning(f"Vision request with model '{model_name}' via SDK failed: {sdk_err}. Trying next candidate...")
                    last_error = sdk_err

        # 2. Fallback path: REST via urllib
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": full_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            },
        }

        for model_name in unique_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        reply_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if reply_text:
                            return {
                                "status": "success",
                                "text": reply_text,
                                "window": win_info,
                                "image_size": (img.width, img.height),
                                "model_used": model_name,
                            }
            except Exception as rest_err:
                logger.warning(f"Vision request with model '{model_name}' via REST failed: {rest_err}")
                last_error = rest_err

        return {
            "status": "error",
            "message": f"Falha na comunicação com o serviço visual: {last_error}",
            "window": win_info,
        }

    def locate_element_coordinates(
        self,
        element_description: str,
        target: str = "janela_ativa",
    ) -> Dict[str, Any]:
        """Locate element on screen using Gemini Vision bounding box detection and map to absolute screen pixels."""
        locate_prompt = (
            f"Localize exatamente o seguinte elemento visual na interface: '{element_description}'.\n"
            "Retorne OBRIGATORIAMENTE um objeto JSON puro no seguinte formato, sem texto antes ou depois:\n"
            "{\n"
            '  "encontrado": true,\n'
            '  "elemento": "nome do elemento identificado",\n'
            '  "tipo": "botao | link | campo_texto | menu | icone",\n'
            '  "box_2d": [ymin, xmin, ymax, xmax],\n'
            '  "confianca": "alta | media | baixa",\n'
            '  "motivo_incerteza": null\n'
            "}\n"
            "Os valores de box_2d devem estar normalizados entre 0 e 1000 (onde 0 é o topo/esquerda e 1000 é base/direita da imagem)."
        )

        result = self.analyze_visual_content(prompt=locate_prompt, target=target)
        if result.get("status") != "success":
            return result

        raw_text = result.get("text", "")

        # Extract JSON from response
        try:
            clean_json = raw_text
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()

            data = json.loads(clean_json)
        except Exception as parse_err:
            logger.warning(f"Could not parse element JSON from vision model ({parse_err}). Raw text: {raw_text[:200]}")
            return {
                "status": "not_found",
                "message": f"Não consegui identificar com certeza o elemento '{element_description}'.",
                "raw_response": raw_text,
                "window": result.get("window"),
            }

        if not data.get("encontrado") or not data.get("box_2d"):
            return {
                "status": "not_found",
                "message": data.get("motivo_incerteza") or f"Elemento '{element_description}' não encontrado na tela.",
                "window": result.get("window"),
            }

        # Calculate absolute screen coordinates from bounding box
        ymin, xmin, ymax, xmax = data["box_2d"]
        img_w, img_h = result["image_size"]
        win_info = result["window"]
        win_rect = win_info.get("rect", (0, 0, img_w, img_h))
        offset_x, offset_y = win_rect[0], win_rect[1]

        # Normalized coordinates [0, 1000] -> local image pixels
        elem_local_x = int(((xmin + xmax) / 2.0 / 1000.0) * img_w)
        elem_local_y = int(((ymin + ymax) / 2.0 / 1000.0) * img_h)

        # Local image pixels -> Absolute desktop screen pixels
        abs_screen_x = offset_x + elem_local_x
        abs_screen_y = offset_y + elem_local_y

        return {
            "status": "success",
            "elemento": data.get("elemento", element_description),
            "tipo": data.get("tipo", "elemento"),
            "confianca": data.get("confianca", "media"),
            "screen_x": abs_screen_x,
            "screen_y": abs_screen_y,
            "window_title": win_info.get("title", ""),
            "box_2d": [ymin, xmin, ymax, xmax],
        }


# Singleton instance
screen_perceiver = ScreenPerceiver()
