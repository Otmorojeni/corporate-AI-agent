from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(default="ok", description="Сервис готов принимать запросы")


class AbbreviationOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(..., ge=1, description="Физический номер страницы в PDF (начиная с 1)")
    quote: str = Field(..., min_length=1, max_length=2000, description="Цитата из текста, подтверждающая расшифровку")


class ExtractedAbbreviation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical: str = Field(..., min_length=1, max_length=128, description="Каноническая форма аббревиатуры")
    expansion: str = Field(..., min_length=1, max_length=512, description="Подтвержденная развернутая форма")
    occurrences: List[AbbreviationOccurrence] = Field(..., min_length=1, max_length=100)


class AbbreviationExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    abbreviations: List[ExtractedAbbreviation] = Field(default_factory=list, max_length=2048)


class AssistantQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(..., min_length=1, max_length=128, description="Уникальный идентификатор запроса")
    query: str = Field(..., min_length=1, max_length=4000, description="Текст вопроса пользователя")


class DetectedTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical: str = Field(..., min_length=1, max_length=128, description="Каноническая аббревиатура")
    expansion: str = Field(..., min_length=1, max_length=512, description="Выбранная расшифровка по контексту")


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(..., min_length=1, max_length=512, description="Путь относительно corpus/, например rosa/manual.pdf")
    page: int = Field(..., ge=1, description="Физический номер страницы")


class AssistantQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(..., min_length=1, max_length=128)
    answer: str = Field(..., min_length=1, max_length=12000, description="Содержательный ответ по базе знаний")
    detected_terms: List[DetectedTerm] = Field(default_factory=list, max_length=16)
    sources: Optional[List[SourceReference]] = Field(default=None, max_length=32)
