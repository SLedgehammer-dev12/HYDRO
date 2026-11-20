import { Button } from "../../components/ui/Button";
import { useSaveTestResult } from "../../hooks/queries";
import { apiErrorMessage, extractRevisionConflict } from "../../lib/api";
import type { Decision, TestType } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";

export function SaveResultButton({
  testType,
  payload,
  decision,
}: {
  testType: TestType;
  payload: Record<string, unknown> | null;
  decision: Decision | undefined;
}) {
  const save = useSaveTestResult();
  const sessionId = useAppStore((state) => state.sessionId);
  const pushToast = useAppStore((state) => state.pushToast);
  const addHistory = useAppStore((state) => state.addHistory);
  if (!payload || !decision) return null;
  return (
    <Button
      loading={save.isPending}
      disabled={!sessionId}
      title={sessionId ? undefined : "Kaydetmek için aktif bir oturum gerekli"}
      onClick={() =>
        save.mutate(
          { testType, payload },
          {
            onSuccess: (outcome) => {
              if (outcome.saved) {
                addHistory({
                  testType,
                  title: decision.title,
                  status: decision.status,
                  summary: decision.summary,
                });
                pushToast("success", "Sonuç oturuma kaydedildi", decision.title);
              } else {
                pushToast("warning", "Sonuç kaydedilemedi", "Sunucu bağlantısı veya oturum yok.");
              }
            },
            onError: (error) => {
              if (!extractRevisionConflict(error)) {
                pushToast("error", "Kaydedilemedi", apiErrorMessage(error));
              }
            },
          },
        )
      }
    >
      Oturuma kaydet
    </Button>
  );
}
