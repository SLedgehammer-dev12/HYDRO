# Agent Rolleri

Bu klasor, proje uzerinde paralel veya sira bazli calisacak agent'lar icin
net sorumluluk sinirlari tanimlar. Her rol tek bir ciktidan sorumludur;
formul, UI ve mimari kararlar birbirine karismasin diye ayrilmistir.

## Harmony Agent'lari (.opencode/harmony/agents/)

OpenCode tarafindan otomatik yuklenen YAML tabanli agent tanimlari:

| Agent | Dosya | Sorumluluk |
|---|---|---|
| Domain Expert | `domain-expert.yaml` | Domain katmani — formul, dataclass, validasyon |
| UI Developer | `ui-developer.yaml` | Tkinter UI — tab, widget, operator akisi |
| Test Writer | `test-writer.yaml` | Test yazimi — birim ve UI workflow testleri |
| Refactoring Architect | `refactoring-architect.yaml` | Kod yapilandirma — modul cikarma, mixin, import temizligi |

## Manuel Roller (agents/roles/)

Elle calistirilan, insan tarafindan yonlendirilen rol tanimlari:

| Rol | Dosya | Sorumluluk |
|---|---|---|
| Calculation Verifier | `calculation-verifier.md` | Formul dogrulama, kabul/red senaryolari |
| Refactor Architect | `refactor-architect.md` | Dosya yerlesimi, modul sinirlari |
| Standard Procedure Analyst | `standard-procedure-analyst.md` | Spec karsilastirmasi, birim analizi |
| UI Ergonomics Reviewer | `ui-ergonomics-reviewer.md` | Operator ergonomisi, hata onleme |

## Harmony Skill'leri (.opencode/harmony/skills/)

| Skill | Amac |
|---|---|
| `add-domain-module` | Yeni domain hesaplama modulu ekleme |
| `extract-ui-mixin` | app_main.py'den mixin cikarma |
| `write-test` | Test yazimi (domain + UI) |
| `modify-ui` | UI elemani ekleme/degistirme |
| `review-quality` | Kod kalitesi ve teknik borc denetimi |
