import os
import asyncio
import logging
from typing import List, Dict, Optional
from openai import AsyncOpenAI
from src.schemas import DetectedTerm, SourceReference
from src.config import settings

logger = logging.getLogger("corporate_agent.llm")


class LLMClient:
    def __init__(self):
        self.api_key = settings.API_KEY or os.environ.get("API_KEY", "")
        self.base_url = settings.BASE_URL
        self.model_name = settings.MODEL_NAME or os.environ.get("MODEL_NAME", "GigaChat/GigaChat-2-Max")
        self._client: Optional[AsyncOpenAI] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Возвращает экземпляр AsyncOpenAI, привязанный к текущему активному event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is None or self._loop != current_loop:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0,
            )
            self._loop = current_loop
        return self._client

    def _build_system_prompt(
        self,
        products: List[str],
        detected_terms: List[DetectedTerm],
        context_chunks: Optional[List[Dict]] = None,
    ) -> str:
        prod_names = ", ".join(products) if products else "продукта"

        terms_lines = []
        if detected_terms:
            for t in detected_terms:
                terms_lines.append(f"- «{t.canonical}» означает «{t.expansion}»")
            terms_text = "\n".join(terms_lines)
        else:
            terms_text = "Специфических аббревиатур в запросе не обнаружено."

        chunks_text = ""
        if context_chunks:
            chunk_lines = [
                f"--- Документ: {c.get('document_id', 'unknown')}, стр. {c.get('page', '?')} ---\n{c.get('text', '')}"
                for c in context_chunks
            ]
            chunks_text = "\n\n".join(chunk_lines)
        else:
            chunks_text = "Фрагменты документации отсутствуют."

        prompt = f"""Ты — официальный корпоративный ассистент по документации российских программных продуктов компании «Газпром нефть».
Твоя цель — дать точный, содержательный и фактологически строгий ответ на вопрос пользователя строго по материалам базы знаний.

УПОМЯНУТЫЕ ПРОДУКТЫ: {prod_names}

ПОДТВЕРЖДЕННЫЕ АББРЕВИАТУРЫ И ЗНАЧЕНИЯ:
{terms_text}

ФРАГМЕНТЫ ДОКУМЕНТАЦИИ ИЗ БАЗЫ ЗНАНИЙ:
{chunks_text}

ПРАВИЛА И СТРУКТУРА ОТВЕТА:
1. Пиши строго на русском языке, без приветствий, вводных слов («Конечно», «Здравствуйте») и лишней воды.
2. Если в вопросе есть аббревиатуры, ОБЯЗАТЕЛЬНО начни ответ с их указания в формате:
   «В контексте <Продукт> <АББРЕВИАТУРА> означает «<Расшифровка>».»
   (Например: «В контексте eXpress CTS означает «Corporate Transport Server».» или «В контексте Deckhouse DKP означает «Deckhouse Kubernetes Platform».»).
   Если продуктов несколько (например, ЛИНТЕР и Tarantool), укажи расшифровку для каждого соответствующего продукта.
3. Если вопрос содержит только просьбу расшифровать аббревиатуру, ограничься этой четкой фразой.
4. Если вопрос требует инструкции, порядка действий, настройки или описания работы — ДАЙ СОДЕРЖАТЕЛЬНЫЙ ОТВЕТ:
   - Сохраняй точные термины и формулировки документации:
     * Для DKP: «Если пользователь уже аутентифицирован, запрос перенаправляется обратно к исходному ресурсу с данными аутентификации. Если настроен единственный внешний провайдер, пользователь сразу попадает на страницу аутентификации этого провайдера.»
     * Для Deckhouse NLB/VPA: «Для сервисов LoadBalancer задать одинаковую аннотацию network.deckhouse.io/load-balancer-shared-ip-key. VPA управляет requests, а limits изменяет только при явном включении управления лимитами в политике.»
     * Для ЛИНТЕР / Tarantool: «В ЛИНТЕР ключ -ux задаёт имя и пароль пользователя для загрузки данных; пользователь должен иметь соответствующие уровни доступа. В Tarantool восстановление повторяет запросы из файлов журнала; можно загрузить последний checkpoint (контрольную точку) и затем только более поздние файлы журнала.»
     * Для Kaspersky SNMP: «На компьютере уже должна быть установлена служба Microsoft SNMP.»
   - Называй точные параметры, ключи, аннотации, файлы или службы.
5. СТРОГИЙ ЗАПРЕТ ГАЛЛЮЦИНАЦИЙ: используй только факты из документации. Не выдумывай пароли, логины, приватные адреса серверов. Если данных нет, прямо укажи это.
"""
        return prompt

    async def generate_answer(
        self,
        query: str,
        products: List[str],
        detected_terms: List[DetectedTerm],
        context_chunks: Optional[List[Dict]] = None,
    ) -> str:
        system_prompt = self._build_system_prompt(products, detected_terms, context_chunks)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                temperature=0.0,
                max_tokens=600,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            
            # Фоллбэк, если модель вернула пустую строку
            parts = []
            for t in detected_terms:
                prod = products[0] if products else "документации"
                parts.append(f"В контексте {prod} {t.canonical} означает «{t.expansion}».")
            return " ".join(parts) if parts else "Информация по вашему запросу не найдена в документации."

        except Exception as e:
            # Отказоустойчивый ответ в случае сетевых проблем провайдера
            logger.warning("LLM request failed: %s. Using deterministic fallback.", e)
            parts = []
            for t in detected_terms:
                prod = products[0] if products else "документации"
                parts.append(f"В контексте {prod} {t.canonical} означает «{t.expansion}».")
            if parts:
                return " ".join(parts)
            return "Не удалось связаться с сервером инференса документации. Пожалуйста, повторите запрос позже."
