"""Hidrostatik test raporlarinin ortak veri semasi.

Bu modul, OCR/elle yuklenen bir saha raporundan cikarilan alanlari ve
uygulamanin hesapladigi degerlerle karsilastirma sonucunu tasiyan temel
veri yapilarini tanimlar. Yalnizca standart kutuphaneye bagimlidir; OCR
servisi (``hidrostatik_test.services.report_ocr``) ve ileride UI bu semayi
kullanir.

Tasarim kararlari:

- Her alan bir :class:`ExtractedField` olarak saklanir. Boylece deger,
  birim, guven skoru, ham metin ve sayfa bilgisi kaybolmaz; insan onayi
  akisinda hangi degerin nereden geldigi gosterilebilir.
- Birimler kanonik hale getirilir: basinc ``bar``, sicaklik ``°C``,
  uzunluk ``mm``/``m``, hacim ``m³``, A ``10^-6/bar``, B ``10^-6/°C``.
- Eksik alan ``None`` olarak kalir; sema "bos deger" ile "sifir"i
  karistirmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 1

SEVERITY_INFO: Final[str] = "info"
SEVERITY_WARNING: Final[str] = "warning"
SEVERITY_CRITICAL: Final[str] = "critical"

UNIT_BAR: Final[str] = "bar"
UNIT_CELSIUS: Final[str] = "°C"
UNIT_MM: Final[str] = "mm"
UNIT_M: Final[str] = "m"
UNIT_M3: Final[str] = "m³"
UNIT_MICRO_PER_BAR: Final[str] = "10^-6/bar"
UNIT_MICRO_PER_C: Final[str] = "10^-6/°C"
UNIT_INVERSE_BAR: Final[str] = "1/bar"
UNIT_INVERSE_C: Final[str] = "1/°C"

#: Kanonik alan adlari -> kullaniciya gosterilecek etiket (ASCII Turkce).
FIELD_LABELS: Final[dict[str, str]] = {
    "report_no": "Rapor No",
    "date": "Tarih",
    "operator": "Operator",
    "section_id": "Bolum No",
    "start_kp": "Bolum baslangic KP",
    "end_kp": "Bolum bitis KP",
    "pipe_od_mm": "Dis cap",
    "pipe_id_mm": "Ic cap",
    "wall_mm": "Et kalinligi",
    "length_m": "Hat uzunlugu",
    "section_volume_m3": "Test bolumu hacmi",
    "max_operating_pressure_bar": "Maksimum isletme basinci",
    "smys_mpa": "Boru akma dayanimi (SMYS)",
    "test_pressure_bar": "Test basinci",
    "air_test.vp": "Hava testi Vp",
    "air_test.vpa": "Hava testi Vpa",
    "air_test.vt": "Hava testi Vt",
    "air_test.k": "Hava testi K",
    "air_test.ratio": "Hava icerik orani ((Vpa/Vp)-1)",
    "air_test.a": "Hava testi A",
    "pressure_test.t_initial": "Baslangic sicakligi",
    "pressure_test.t_final": "Bitis sicakligi",
    "pressure_test.delta_t": "Sicaklik farki (dT)",
    "pressure_test.p_delta": "Sicaklik kaynakli basinc degisimi (dP)",
    "pressure_test.pa": "Basinc dususu (Pa)",
    "pressure_test.pl": "Izin verilen basinc degisimi (PL)",
    "pressure_test.a": "Basinc testi A",
    "pressure_test.b": "Basinc testi B",
    "result": "Sonuc",
    "notes": "Notlar",
}

#: Turkce/Ingilizce etiket eslemesi. OCR servisi bu listeyi kullanir.
FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "report_no": (
        "Rapor No",
        "Rapor Numarasi",
        "Rapor Numarası",
        "Report No",
        "Report Number",
        "Test No",
        "Belge No",
        "Form No",
    ),
    "date": (
        "Test Tarihi",
        "Rapor Tarihi",
        "Tarih",
        "Test Date",
        "Date",
    ),
    "operator": (
        "Operatör Adı",
        "Operatör",
        "Operator",
        "Test Sorumlusu",
        "Saha Sorumlusu",
        "Gözetmen",
        "Inspector",
        "Tester",
    ),
    "section_id": (
        "Test Bölüm No",
        "Test Bolum No",
        "Bölüm No",
        "Bolum No",
        "Kesim No",
        "Hat Kesimi",
        "Section No",
        "Section",
        "Segment No",
    ),
    "start_kp": (
        "Test Bölümünün Başlangıç Noktası",
        "Başlangıç Noktası",
        "Başlangıç KP",
        "Baslangic KP",
        "1.Başlık Yeri",
        "1. Başlık Yeri",
        "Start KP",
        "Start Chainage",
    ),
    "end_kp": (
        "Test Bölümünün Bitiş Noktası",
        "Bitiş Noktası",
        "Bitiş KP",
        "Bitis KP",
        "2.Başlık Yeri",
        "2. Başlık Yeri",
        "End KP",
        "End Chainage",
    ),
    "pipe_od_mm": (
        "Boru Dış Çapı",
        "Dış Çap",
        "Dış Çapı",
        "Dis Cap",
        "Outside Diameter",
        "Pipe OD",
        "OD",
        "Çap",
        "Cap",
    ),
    "wall_mm": (
        "Boru Et Kalınlığı",
        "Boru Et Kalinligi",
        "Et Kalınlığı",
        "Et Kalinligi",
        "Duvar Kalınlığı",
        "Cidar Kalınlığı",
        "Wall Thickness",
        "Wall",
        "Et",
        "Cidar",
        "WT",
    ),
    "pipe_id_mm": (
        "Boru İç Çapı",
        "Boru Ic Capi",
        "İç Çap",
        "Ic Cap",
        "Inner Diameter",
        "Inside Diameter",
        "Pipe ID",
    ),
    "length_m": (
        "Test Bölüm Boyu",
        "Test Bolum Boyu",
        "Test Bölümü Boyu",
        "Bölüm Uzunluğu",
        "Bolum Uzunlugu",
        "Test Uzunluğu",
        "Hat Uzunluğu",
        "Test Length",
        "Uzunluk",
        "Length",
    ),
    "section_volume_m3": (
        "Test Bölüm Hacmi",
        "Test Bolum Hacmi",
        "Test Bölümü Hacmi",
        "Bölüm Hacmi",
        "Geometrik Hacim",
        "Vt",
        "V t",
    ),
    "max_operating_pressure_bar": (
        "Maksimum İşletme Basıncı",
        "Maks. İşletme Basıncı",
        "Maksimum Isletme Basinci",
        "Maks. Isletme Basinci",
        "Maximum İşletme Basıncı",
        "İşletme Basıncı",
        "MAOP",
    ),
    "smys_mpa": (
        "Boru Akma Dayanımı (SMYS)",
        "Boru Akma Dayanımı",
        "Boru Akma Dayanimi",
        "Akma Dayanımı",
        "SMYS",
    ),
    "test_pressure_bar": (
        "Maksimum Test Basıncı",
        "Maks. Test Basıncı",
        "Maximum Test Basıncı",
        "Maksimum Test Basinci",
        "Maks. Test Basinci",
        "Hidrostatik Test Basıncı",
        "Mukavemet Basıncı",
        "Test Basıncı",
        "Test Basinci",
        "Deney Basıncı",
        "Test Pressure",
        "Ptest",
        "P Test",
    ),
    "air_test.vp": (
        "Teorik İlave Su",
        "Teorik Hacim",
        "Theoretical Added Water",
        "Theoretical Volume",
        "Vp",
    ),
    "air_test.vpa": (
        "Fiili İlave Su",
        "Fiili Hacim",
        "Gerçek Hacim",
        "Actual Added Water",
        "Actual Volume",
        "Vpa",
    ),
    "air_test.vt": (
        "Test Bölümünün Geometrik Hacmi",
        "Geometrik Hacmi",
        "Hava testi Vt",
    ),
    "air_test.k": (
        "Katsayı,Dikişsiz Borular İçin 1,Kaynaklı Borular İçin 1,02",
        "Katsayı, Dikişsiz Borular İçin 1, Kaynaklı Borular İçin 1,02",
        "K katsayısı",
        "Katsayı (K)",
    ),
    "air_test.ratio": (
        "(Vpa/Vp)-1",
        "(Vpa/Vp) - 1",
        "Vpa/Vp",
        "Hava içerik oranı",
        "Air content ratio",
    ),
    "air_test.a": (
        "Suyun İzotermal Sıkıştırılabilirlik Katsayısı",
        "Suyun İzotermal Sıkışabilirlik Katsayısı",
        "Sıkıştırılabilirlik Katsayısı",
        "A (hava)",
        "A",
    ),
    "pressure_test.t_initial": (
        "Başlangıç Sıcaklığı",
        "İlk Sıcaklık",
        "Initial Temperature",
        "T İlk",
        "Tilk",
        "T1",
    ),
    "pressure_test.t_final": (
        "Bitiş Sıcaklığı",
        "Son Sıcaklık",
        "Final Temperature",
        "T Son",
        "Tson",
        "T2",
    ),
    "pressure_test.delta_t": (
        "Testin Başı ve Sonunda Su Sıcaklığında Oluşan Değişim",
        "Testin Basinda ve Sonunda Su Sicakliginda Olusan Degisim",
        "Sıcaklık Farkı",
        "Temperature Difference",
        "Temperature Change",
        "Delta T",
        "ΔT",
        "dT",
    ),
    "pressure_test.p_delta": (
        "Sıcaklık Değişiminden Kaynaklanan Basınç Değişimi",
        "Sicaklik Degisiminden Kaynaklanan Basinc Degisimi",
        "Sıcaklık Kaynaklı Basınç Değişimi",
        "ΔP",
        "dP",
        "AP",
    ),
    "pressure_test.pl": (
        "Test Boyunca İzin Verilebilir Basınç Değişimi",
        "İzin Verilebilir Basınç Değişimi",
        "Izin Verilebilir Basinc Degisimi",
        "PL",
    ),
    "pressure_test.pa": (
        "Ölçülen Basınç Değişimi",
        "Olculen Basinc Degisimi",
        "Basınç Düşüşü",
        "Basınç Farkı",
        "Pressure Drop",
        "Pa",
    ),
    "pressure_test.a": (
        "Suyun İzotermal Sıkıştırılabilirlik Katsayısı",
        "Suyun İzotermal Sıkışabilirlik Katsayısı",
        "Sıkıştırılabilirlik Katsayısı",
        "A (basınç)",
        "A",
    ),
    "pressure_test.b": (
        "Su ve Çeliğin Isıl Genleşme Katsayıları Arasındaki Fark",
        "Isıl Genleşme Katsayıları Arasındaki Fark",
        "B Katsayısı",
        "B Coefficient",
        "B",
    ),
    "result": (
        "Test Sonucu",
        "Sonuç",
        "Sonuc",
        "Durum",
        "Karar",
        "Result",
        "Status",
        "Verdict",
    ),
    "notes": (
        "Açıklama",
        "Notlar",
        "Not",
        "Remarks",
        "Comment",
        "Notes",
    ),
}

#: Raporun karsilastirma yapilabilmesi icin zorunlu alanlar.
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "pipe_od_mm",
    "wall_mm",
    "length_m",
    "test_pressure_bar",
)

#: Zorunlu olmayan ama insan incelemesinde beklenen alanlar.
RECOMMENDED_FIELDS: Final[tuple[str, ...]] = (
    "report_no",
    "date",
    "air_test.vp",
    "air_test.vpa",
    "pressure_test.t_initial",
    "pressure_test.t_final",
    "pressure_test.delta_t",
    "pressure_test.pa",
    "result",
)

OPTIONAL_FIELDS: Final[tuple[str, ...]] = (
    "operator",
    "section_id",
    "start_kp",
    "end_kp",
    "pipe_id_mm",
    "section_volume_m3",
    "max_operating_pressure_bar",
    "smys_mpa",
    "air_test.vt",
    "air_test.k",
    "air_test.ratio",
    "air_test.a",
    "pressure_test.p_delta",
    "pressure_test.pl",
    "pressure_test.a",
    "pressure_test.b",
    "notes",
)

ALL_FIELDS: Final[tuple[str, ...]] = REQUIRED_FIELDS + RECOMMENDED_FIELDS + OPTIONAL_FIELDS

#: Birim yazim eslemeleri. Anahtar kucuk harfe cevrilerek aranir.
_UNIT_ALIASES: Final[dict[str, str]] = {
    "bar": UNIT_BAR,
    "bars": UNIT_BAR,
    "barg": UNIT_BAR,
    "bara": UNIT_BAR,
    "°c": UNIT_CELSIUS,
    "ºc": UNIT_CELSIUS,
    "c": UNIT_CELSIUS,
    "degc": UNIT_CELSIUS,
    "celsius": UNIT_CELSIUS,
    "°f": "°F",
    "ºf": "°F",
    "f": "°F",
    "degf": "°F",
    "fahrenheit": "°F",
    "k": "K",
    "kelvin": "K",
    "mm": UNIT_MM,
    "millimeter": UNIT_MM,
    "millimetre": UNIT_MM,
    "cm": "cm",
    "m": UNIT_M,
    "meter": UNIT_M,
    "metre": UNIT_M,
    "km": "km",
    "in": "in",
    "inch": "in",
    "inç": "in",
    '"': "in",
    "″": "in",
    "ft": "ft",
    "feet": "ft",
    "m³": UNIT_M3,
    "m3": UNIT_M3,
    "m^3": UNIT_M3,
    "cubic meter": UNIT_M3,
    "l": "L",
    "lt": "L",
    "litre": "L",
    "liter": "L",
    "ml": "mL",
    "milliliter": "mL",
    "psi": "psi",
    "kpa": "kPa",
    "mpa": "MPa",
    "%": "%",
    "1/bar": UNIT_INVERSE_BAR,
    "bar^-1": UNIT_INVERSE_BAR,
    "bar-1": UNIT_INVERSE_BAR,
    "1/°c": UNIT_INVERSE_C,
    "1/c": UNIT_INVERSE_C,
    "1/k": UNIT_INVERSE_C,
    "10^-6/bar": UNIT_MICRO_PER_BAR,
    "10-6/bar": UNIT_MICRO_PER_BAR,
    "1e-6/bar": UNIT_MICRO_PER_BAR,
    "micro/bar": UNIT_MICRO_PER_BAR,
    "µ/bar": UNIT_MICRO_PER_BAR,
    "u/bar": UNIT_MICRO_PER_BAR,
    "10^-6/°c": UNIT_MICRO_PER_C,
    "10-6/°c": UNIT_MICRO_PER_C,
    "1e-6/°c": UNIT_MICRO_PER_C,
    "micro/°c": UNIT_MICRO_PER_C,
    "µ/°c": UNIT_MICRO_PER_C,
    "u/°c": UNIT_MICRO_PER_C,
}

_LENGTH_FACTORS_TO_MM: Final[dict[str, float]] = {
    UNIT_MM: 1.0,
    "cm": 10.0,
    UNIT_M: 1000.0,
    "km": 1_000_000.0,
    "in": 25.4,
    "ft": 304.8,
}

_PRESSURE_FACTORS_TO_BAR: Final[dict[str, float]] = {
    UNIT_BAR: 1.0,
    "kPa": 0.01,
    "MPa": 10.0,
    "psi": 0.06894757293168361,
}

_VOLUME_FACTORS_TO_M3: Final[dict[str, float]] = {
    UNIT_M3: 1.0,
    "L": 1e-3,
    "mL": 1e-6,
    "cm3": 1e-6,
}

_INVERSE_BAR_FACTORS: Final[dict[str, float]] = {
    UNIT_MICRO_PER_BAR: 1e-6,
    UNIT_INVERSE_BAR: 1.0,
}

_INVERSE_C_FACTORS: Final[dict[str, float]] = {
    UNIT_MICRO_PER_C: 1e-6,
    UNIT_INVERSE_C: 1.0,
}


def normalize_unit(unit: str) -> str:
    """Return a canonical unit label for ``unit``.

    Bilinmeyen birimler yalnizca bosluklari temizlenerek geri dondurulur;
    boylece sema bilinmeyen etiketi kaybetmez.
    """

    if not unit:
        return ""
    text = " ".join(str(unit).strip().replace("º", "°").split())
    key = text.casefold().replace(" ", "")
    if key in _UNIT_ALIASES:
        return _UNIT_ALIASES[key]
    # "° C", "m ^ 3" gibi bosluklu yazimlar
    compact = text.casefold().replace(" ", "")
    return _UNIT_ALIASES.get(compact, text)


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between supported units.

    Desteklenen boyutlar: basinc, uzunluk, hacim, ters-sikistirilabilirlik
    ve sicaklik. Uyumsuz birimlerde ``ValueError`` yukseltilir.
    """

    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    if not source or not target:
        raise ValueError("Birim bos olamaz.")
    if source == target:
        return float(value)

    if source in (UNIT_CELSIUS, "°F", "K") and target in (UNIT_CELSIUS, "°F", "K"):
        return _convert_temperature(float(value), source, target)

    if source in _LENGTH_FACTORS_TO_MM and target in _LENGTH_FACTORS_TO_MM:
        return float(value) * _LENGTH_FACTORS_TO_MM[source] / _LENGTH_FACTORS_TO_MM[target]

    if source in _PRESSURE_FACTORS_TO_BAR and target in _PRESSURE_FACTORS_TO_BAR:
        return float(value) * _PRESSURE_FACTORS_TO_BAR[source] / _PRESSURE_FACTORS_TO_BAR[target]

    if source in _VOLUME_FACTORS_TO_M3 and target in _VOLUME_FACTORS_TO_M3:
        return float(value) * _VOLUME_FACTORS_TO_M3[source] / _VOLUME_FACTORS_TO_M3[target]

    if source in _INVERSE_BAR_FACTORS and target in _INVERSE_BAR_FACTORS:
        return float(value) * _INVERSE_BAR_FACTORS[source] / _INVERSE_BAR_FACTORS[target]

    if source in _INVERSE_C_FACTORS and target in _INVERSE_C_FACTORS:
        return float(value) * _INVERSE_C_FACTORS[source] / _INVERSE_C_FACTORS[target]

    raise ValueError(f"Uyumsuz birimler: {from_unit!r} -> {to_unit!r}")


def convert_temperature_delta(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a temperature *difference* (offset uygulanmaz)."""

    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    if source == target:
        return float(value)
    factors = {UNIT_CELSIUS: 1.0, "K": 1.0, "°F": 5.0 / 9.0}
    if source not in factors or target not in factors:
        raise ValueError(f"Uyumsuz sicaklik farki birimleri: {from_unit!r} -> {to_unit!r}")
    return float(value) * factors[source] / factors[target]


def _convert_temperature(value: float, source: str, target: str) -> float:
    if source == target:
        return value
    celsius = {
        UNIT_CELSIUS: value,
        "K": value - 273.15,
        "°F": (value - 32.0) * 5.0 / 9.0,
    }[source]
    return {
        UNIT_CELSIUS: celsius,
        "K": celsius + 273.15,
        "°F": celsius * 9.0 / 5.0 + 32.0,
    }[target]


@dataclass(frozen=True)
class ExtractedField:
    """A single value extracted from a report, with provenance."""

    value: float | str | None
    unit: str = ""
    confidence: float = 0.0
    raw_text: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Guven skoru 0.0 ile 1.0 arasinda olmalidir.")
        object.__setattr__(self, "confidence", confidence)
        if self.unit:
            object.__setattr__(self, "unit", normalize_unit(self.unit))
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError("bbox dort elemanli olmalidir: (x0, y0, x1, y1).")

    def as_float(self) -> float | None:
        """Return the numeric value, or ``None`` when the field is textual."""

        if self.value is None or isinstance(self.value, bool):
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        try:
            return float(str(self.value).replace(",", ".").strip())
        except ValueError:
            return None

    def is_low_confidence(self, threshold: float = 0.6) -> bool:
        return self.confidence < threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "confidence": round(self.confidence, 4),
            "raw_text": self.raw_text,
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExtractedField | None:
        if not data:
            return None
        bbox = data.get("bbox")
        return cls(
            value=data.get("value"),
            unit=str(data.get("unit") or ""),
            confidence=float(data.get("confidence") or 0.0),
            raw_text=str(data.get("raw_text") or ""),
            page=data.get("page"),
            bbox=tuple(bbox) if bbox else None,
        )


@dataclass(frozen=True)
class AirTestFields:
    """Madde 13 hava icerik testi alanlari (Vp, Vpa, A)."""

    vp: ExtractedField | None = None
    vpa: ExtractedField | None = None
    vt: ExtractedField | None = None
    k: ExtractedField | None = None
    ratio: ExtractedField | None = None
    a: ExtractedField | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vp": self.vp.to_dict() if self.vp else None,
            "vpa": self.vpa.to_dict() if self.vpa else None,
            "vt": self.vt.to_dict() if self.vt else None,
            "k": self.k.to_dict() if self.k else None,
            "ratio": self.ratio.to_dict() if self.ratio else None,
            "a": self.a.to_dict() if self.a else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AirTestFields:
        data = data or {}
        return cls(
            vp=ExtractedField.from_dict(data.get("vp")),
            vpa=ExtractedField.from_dict(data.get("vpa")),
            vt=ExtractedField.from_dict(data.get("vt")),
            k=ExtractedField.from_dict(data.get("k")),
            ratio=ExtractedField.from_dict(data.get("ratio")),
            a=ExtractedField.from_dict(data.get("a")),
        )


@dataclass(frozen=True)
class PressureTestFields:
    """Madde 15 basinc testi alanlari (Tilk, Tson, dT, Pa, A, B)."""

    t_initial: ExtractedField | None = None
    t_final: ExtractedField | None = None
    delta_t: ExtractedField | None = None
    p_delta: ExtractedField | None = None
    pa: ExtractedField | None = None
    pl: ExtractedField | None = None
    a: ExtractedField | None = None
    b: ExtractedField | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "t_initial": self.t_initial.to_dict() if self.t_initial else None,
            "t_final": self.t_final.to_dict() if self.t_final else None,
            "delta_t": self.delta_t.to_dict() if self.delta_t else None,
            "p_delta": self.p_delta.to_dict() if self.p_delta else None,
            "pa": self.pa.to_dict() if self.pa else None,
            "pl": self.pl.to_dict() if self.pl else None,
            "a": self.a.to_dict() if self.a else None,
            "b": self.b.to_dict() if self.b else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PressureTestFields:
        data = data or {}
        return cls(
            t_initial=ExtractedField.from_dict(data.get("t_initial")),
            t_final=ExtractedField.from_dict(data.get("t_final")),
            delta_t=ExtractedField.from_dict(data.get("delta_t")),
            p_delta=ExtractedField.from_dict(data.get("p_delta")),
            pa=ExtractedField.from_dict(data.get("pa")),
            pl=ExtractedField.from_dict(data.get("pl")),
            a=ExtractedField.from_dict(data.get("a")),
            b=ExtractedField.from_dict(data.get("b")),
        )


@dataclass(frozen=True)
class ValidationIssue:
    """Sema dogrulamasinda bulunan tek bir sorun."""

    field: str
    code: str
    message: str
    severity: str = SEVERITY_WARNING

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class HydrotestReport:
    """Bir saha raporundan cikarilan hidrostatik test verileri."""

    report_no: ExtractedField | None = None
    date: ExtractedField | None = None
    operator: ExtractedField | None = None
    section_id: ExtractedField | None = None
    start_kp: ExtractedField | None = None
    end_kp: ExtractedField | None = None
    pipe_od_mm: ExtractedField | None = None
    pipe_id_mm: ExtractedField | None = None
    wall_mm: ExtractedField | None = None
    length_m: ExtractedField | None = None
    section_volume_m3: ExtractedField | None = None
    max_operating_pressure_bar: ExtractedField | None = None
    smys_mpa: ExtractedField | None = None
    test_pressure_bar: ExtractedField | None = None
    air_test: AirTestFields = field(default_factory=AirTestFields)
    pressure_test: PressureTestFields = field(default_factory=PressureTestFields)
    result: ExtractedField | None = None
    notes: ExtractedField | None = None
    warnings: tuple[str, ...] = ()

    def iter_fields(self) -> list[tuple[str, ExtractedField]]:
        """Return ``(canonical_key, field)`` pairs for all present fields."""

        pairs: list[tuple[str, ExtractedField]] = []
        for key in ALL_FIELDS:
            extracted = self.get_field(key)
            if extracted is not None:
                pairs.append((key, extracted))
        return pairs

    def get_field(self, key: str) -> ExtractedField | None:
        if key.startswith("air_test."):
            return getattr(self.air_test, key.split(".", 1)[1], None)
        if key.startswith("pressure_test."):
            return getattr(self.pressure_test, key.split(".", 1)[1], None)
        return getattr(self, key, None)

    def missing_required_fields(self) -> list[str]:
        return [key for key in REQUIRED_FIELDS if self.get_field(key) is None]

    def average_confidence(self) -> float:
        confidences = [component.confidence for _, component in self.iter_fields()]
        if not confidences:
            return 0.0
        return sum(confidences) / len(confidences)

    def is_complete(self) -> bool:
        return not self.missing_required_fields()

    def validation_issues(self) -> list[ValidationIssue]:
        return validate_report(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_no": self.report_no.to_dict() if self.report_no else None,
            "date": self.date.to_dict() if self.date else None,
            "operator": self.operator.to_dict() if self.operator else None,
            "section_id": self.section_id.to_dict() if self.section_id else None,
            "start_kp": self.start_kp.to_dict() if self.start_kp else None,
            "end_kp": self.end_kp.to_dict() if self.end_kp else None,
            "pipe_od_mm": self.pipe_od_mm.to_dict() if self.pipe_od_mm else None,
            "pipe_id_mm": self.pipe_id_mm.to_dict() if self.pipe_id_mm else None,
            "wall_mm": self.wall_mm.to_dict() if self.wall_mm else None,
            "length_m": self.length_m.to_dict() if self.length_m else None,
            "section_volume_m3": (
                self.section_volume_m3.to_dict() if self.section_volume_m3 else None
            ),
            "max_operating_pressure_bar": (
                self.max_operating_pressure_bar.to_dict()
                if self.max_operating_pressure_bar
                else None
            ),
            "smys_mpa": self.smys_mpa.to_dict() if self.smys_mpa else None,
            "test_pressure_bar": (
                self.test_pressure_bar.to_dict() if self.test_pressure_bar else None
            ),
            "air_test": self.air_test.to_dict(),
            "pressure_test": self.pressure_test.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "notes": self.notes.to_dict() if self.notes else None,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HydrotestReport:
        data = data or {}
        warnings = data.get("warnings") or ()
        return cls(
            report_no=ExtractedField.from_dict(data.get("report_no")),
            date=ExtractedField.from_dict(data.get("date")),
            operator=ExtractedField.from_dict(data.get("operator")),
            section_id=ExtractedField.from_dict(data.get("section_id")),
            start_kp=ExtractedField.from_dict(data.get("start_kp")),
            end_kp=ExtractedField.from_dict(data.get("end_kp")),
            pipe_od_mm=ExtractedField.from_dict(data.get("pipe_od_mm")),
            pipe_id_mm=ExtractedField.from_dict(data.get("pipe_id_mm")),
            wall_mm=ExtractedField.from_dict(data.get("wall_mm")),
            length_m=ExtractedField.from_dict(data.get("length_m")),
            section_volume_m3=ExtractedField.from_dict(data.get("section_volume_m3")),
            max_operating_pressure_bar=ExtractedField.from_dict(
                data.get("max_operating_pressure_bar")
            ),
            smys_mpa=ExtractedField.from_dict(data.get("smys_mpa")),
            test_pressure_bar=ExtractedField.from_dict(data.get("test_pressure_bar")),
            air_test=AirTestFields.from_dict(data.get("air_test")),
            pressure_test=PressureTestFields.from_dict(data.get("pressure_test")),
            result=ExtractedField.from_dict(data.get("result")),
            notes=ExtractedField.from_dict(data.get("notes")),
            warnings=tuple(str(item) for item in warnings),
        )


def validate_report(
    report: HydrotestReport,
    *,
    min_confidence: float = 0.6,
) -> list[ValidationIssue]:
    """Return schema/physics validation issues for ``report``.

    Dogrulama rapordaki *degerleri degistirmez*; yalnizca insan onayina
    sunulacak uyarilari uretir.
    """

    issues: list[ValidationIssue] = []
    present = dict(report.iter_fields())

    for key in REQUIRED_FIELDS:
        if key not in present:
            issues.append(
                ValidationIssue(
                    field=key,
                    code="missing_required",
                    message=f"Zorunlu alan eksik: {FIELD_LABELS[key]}.",
                    severity=SEVERITY_CRITICAL,
                )
            )

    if not present:
        issues.append(
            ValidationIssue(
                field="",
                code="no_fields",
                message="Raporda taninabilir hicbir alan bulunamadi.",
                severity=SEVERITY_CRITICAL,
            )
        )
        return issues

    od = _numeric(report.pipe_od_mm)
    wall = _numeric(report.wall_mm)
    length = _numeric(report.length_m)
    pressure = _numeric(report.test_pressure_bar)

    if od is not None and od <= 0:
        issues.append(_invalid("pipe_od_mm", "Dis cap sifirdan buyuk olmalidir."))
    if wall is not None and wall <= 0:
        issues.append(_invalid("wall_mm", "Et kalinligi sifirdan buyuk olmalidir."))
    if length is not None and length <= 0:
        issues.append(_invalid("length_m", "Hat uzunlugu sifirdan buyuk olmalidir."))
    if pressure is not None and pressure <= 0:
        issues.append(_invalid("test_pressure_bar", "Test basinci sifirdan buyuk olmalidir."))

    if od is not None and wall is not None and wall > 0 and wall * 2 >= od:
        issues.append(
            ValidationIssue(
                field="wall_mm",
                code="inconsistent_geometry",
                message="Et kalinligi ic capi sifira dusurecek kadar buyuk.",
                severity=SEVERITY_CRITICAL,
            )
        )

    vp = _numeric(report.air_test.vp)
    vpa = _numeric(report.air_test.vpa)
    if vp is not None and vp <= 0:
        issues.append(_invalid("air_test.vp", "Vp sifirdan buyuk olmalidir."))
    if vpa is not None and vpa < 0:
        issues.append(_invalid("air_test.vpa", "Vpa negatif olamaz."))
    if vp is not None and vpa is not None and vp > 0 and vpa >= vp * 1.06:
        issues.append(
            ValidationIssue(
                field="air_test.vpa",
                code="air_test_limit_exceeded",
                message=(
                    "Vpa, Vp'nin %6 kabul sinirini asiyor; hava icerik testi "
                    "sartnameye gore basarisiz gorunuyor."
                ),
                severity=SEVERITY_CRITICAL,
            )
        )

    t_initial = _numeric(report.pressure_test.t_initial)
    t_final = _numeric(report.pressure_test.t_final)
    delta_t = _numeric(report.pressure_test.delta_t)
    if t_initial is not None and t_final is not None and delta_t is not None:
        expected = t_initial - t_final
        if abs(expected - delta_t) > 0.1:
            issues.append(
                ValidationIssue(
                    field="pressure_test.delta_t",
                    code="delta_t_mismatch",
                    message=(
                        "dT, Tilk - Tson ile tutarsiz: "
                        f"Tilk-Tson={expected:.3f} °C, rapordaki dT={delta_t:.3f} °C."
                    ),
                    severity=SEVERITY_WARNING,
                )
            )

    for key, extracted in present.items():
        if extracted.confidence < min_confidence:
            issues.append(
                ValidationIssue(
                    field=key,
                    code="low_confidence",
                    message=(
                        f"{FIELD_LABELS.get(key, key)} alani dusuk guvenle okundu "
                        f"({extracted.confidence:.0%}); insan onayi gerekli."
                    ),
                    severity=SEVERITY_WARNING,
                )
            )

    if report.result is None:
        issues.append(
            ValidationIssue(
                field="result",
                code="missing_result",
                message="Rapor sonucu (PASS/FAIL) okunamadi; insan onayi gerekli.",
                severity=SEVERITY_INFO,
            )
        )
    else:
        value = str(report.result.value or "").strip().upper()
        if value not in {"PASS", "FAIL"}:
            issues.append(
                ValidationIssue(
                    field="result",
                    code="unknown_result",
                    message=f"Rapor sonucu taninmadi: {report.result.value!r}.",
                    severity=SEVERITY_WARNING,
                )
            )

    if report.date is not None:
        value = str(report.date.value or "")
        try:
            _date.fromisoformat(value)
        except ValueError:
            issues.append(
                ValidationIssue(
                    field="date",
                    code="invalid_date",
                    message=f"Tarih ISO formatina cevrilemedi: {value!r}.",
                    severity=SEVERITY_WARNING,
                )
            )

    return issues


def _numeric(extracted: ExtractedField | None) -> float | None:
    return extracted.as_float() if extracted is not None else None


def _invalid(field_key: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        field=field_key,
        code="invalid_value",
        message=message,
        severity=SEVERITY_CRITICAL,
    )


__all__ = [
    "ALL_FIELDS",
    "AirTestFields",
    "ExtractedField",
    "FIELD_ALIASES",
    "FIELD_LABELS",
    "HydrotestReport",
    "OPTIONAL_FIELDS",
    "PressureTestFields",
    "RECOMMENDED_FIELDS",
    "REQUIRED_FIELDS",
    "SCHEMA_VERSION",
    "SEVERITY_CRITICAL",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "UNIT_BAR",
    "UNIT_CELSIUS",
    "UNIT_INVERSE_BAR",
    "UNIT_INVERSE_C",
    "UNIT_M",
    "UNIT_M3",
    "UNIT_MICRO_PER_BAR",
    "UNIT_MICRO_PER_C",
    "UNIT_MM",
    "ValidationIssue",
    "convert_temperature_delta",
    "convert_unit",
    "normalize_unit",
    "validate_report",
]
