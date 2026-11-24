import type { BotasFormCode } from "../../lib/types";

export interface FormDraftRecord {
  formDate: string;
  extractedData: Record<string, unknown>;
  baseRevision: number | null;
  savedAt: string;
}

const DRAFT_PREFIX = "hydro-form-draft-v1";

function draftKey(sessionId: string, formCode: BotasFormCode): string {
  return `${DRAFT_PREFIX}:${sessionId}:${formCode}`;
}

export function saveFormDraft(
  sessionId: string,
  formCode: BotasFormCode,
  draft: FormDraftRecord,
): void {
  try {
    localStorage.setItem(draftKey(sessionId, formCode), JSON.stringify(draft));
  } catch {
    /* localStorage kota/gizlilik modu hatalarını sessizce yoksay */
  }
}

export function loadFormDraft(
  sessionId: string,
  formCode: BotasFormCode,
): FormDraftRecord | null {
  try {
    const raw = localStorage.getItem(draftKey(sessionId, formCode));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<FormDraftRecord> | null;
    if (
      !parsed ||
      typeof parsed !== "object" ||
      typeof parsed.formDate !== "string" ||
      !parsed.extractedData ||
      typeof parsed.extractedData !== "object" ||
      Array.isArray(parsed.extractedData)
    ) {
      return null;
    }
    return {
      formDate: parsed.formDate,
      extractedData: parsed.extractedData,
      baseRevision: typeof parsed.baseRevision === "number" ? parsed.baseRevision : null,
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function clearFormDraft(sessionId: string, formCode: BotasFormCode): void {
  try {
    localStorage.removeItem(draftKey(sessionId, formCode));
  } catch {
    /* yoksay */
  }
}
