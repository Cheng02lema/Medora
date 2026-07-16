import { useWorkbench } from "../store/workbench";

export default function ToastContainer() {
  const toasts = useWorkbench((s) => s.toasts);
  const removeToast = useWorkbench((s) => s.removeToast);

  const icons: Record<string, string> = {
    success: "✓",
    error: "×",
    info: "i",
    warning: "!",
  };

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast ${t.type}`}
          onClick={() => removeToast(t.id)}
          style={{ cursor: "pointer" }}
        >
          <span>{icons[t.type] || "•"}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
