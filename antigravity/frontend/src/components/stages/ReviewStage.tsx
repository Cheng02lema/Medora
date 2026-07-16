import { useState, useRef, useEffect } from "react";
import { useWorkbench } from "../../store/workbench";

interface ExtractedField {
  value: any;
  original_value?: any;
  edited?: boolean;
}

export default function ReviewStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const currentPatientId = useWorkbench((s) => s.currentPatientId);
  const updateReview = useWorkbench((s) => s.updateReview);

  const [filterUnedited, setFilterUnedited] = useState(false);
  const [filterFlagged, setFilterFlagged] = useState(false);
  const [searchField, setSearchField] = useState("");
  const [localNotes, setLocalNotes] = useState<Record<string, string>>({});
  const noteTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    return () => {
      Object.values(noteTimers.current).forEach(clearTimeout);
    };
  }, []);

  if (!patientDetail || !currentPatientId) return null;

  const extracted = patientDetail.extracted_fields;
  if (!extracted) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">尚未抽取</div>
        <div className="empty-desc">需要先完成抽取，才能进行审核</div>
      </div>
    );
  }

  const fields: Record<string, ExtractedField> = extracted.fields || {};
  const reviewData = patientDetail.stages["review"]?.data?.reviewed_fields || {};

  let entries = Object.entries(fields);
  if (filterUnedited) {
    entries = entries.filter(([, v]) => !(typeof v === "object" && v !== null && v.edited));
  }
  if (filterFlagged) {
    entries = entries.filter(([name]) => reviewData[name]?.flagged);
  }
  if (searchField.trim()) {
    entries = entries.filter(([name]) => name.toLowerCase().includes(searchField.toLowerCase()));
  }

  const reviewedCount = Object.entries(reviewData).filter(([, v]: any) => v?.reviewed).length;
  const flaggedCount = Object.entries(reviewData).filter(([, v]: any) => v?.flagged).length;
  const total = Object.keys(fields).length;

  const handleReviewField = (name: string, reviewed: boolean) => {
    updateReview(currentPatientId, {
      ...reviewData,
      [name]: {
        reviewed,
        flagged: !reviewed,
        note: localNotes[name] ?? reviewData[name]?.note ?? "",
      },
    }, false);
  };

  const handleAllReviewed = () => {
    if (!confirm(`确认将全部 ${total} 个字段标记为已审？`)) return;
    const all: Record<string, any> = {};
    for (const [name] of Object.entries(fields)) {
      all[name] = {
        reviewed: true,
        flagged: false,
        note: localNotes[name] ?? reviewData[name]?.note ?? "",
      };
    }
    updateReview(currentPatientId, all, true);
  };

  const handleNoteChange = (name: string, note: string) => {
    setLocalNotes((prev) => ({ ...prev, [name]: note }));
    if (noteTimers.current[name]) clearTimeout(noteTimers.current[name]);
    noteTimers.current[name] = setTimeout(() => {
      updateReview(currentPatientId, {
        ...reviewData,
        [name]: {
          reviewed: !!reviewData[name]?.reviewed,
          flagged: !!reviewData[name]?.flagged,
          note,
        },
      }, false);
    }, 600);
  };

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div className="h2">审核 ({reviewedCount}/{total})</div>
        {flaggedCount > 0 && (
          <span style={{ fontSize: 11, color: "var(--warning)", padding: "2px 8px", borderRadius: 4, background: "var(--warning-fade)" }}>
            {flaggedCount} 项待查
          </span>
        )}
        <div className="progress-bar" style={{ width: 120, height: 4 }}>
          <div className="progress-fill" style={{ width: `${total ? (reviewedCount / total) * 100 : 0}%` }} />
        </div>
        <div style={{ flex: 1 }} />
        <input
          value={searchField}
          onChange={(e) => setSearchField(e.target.value)}
          placeholder="搜索字段…"
          style={{ width: 140 }}
        />
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, cursor: "pointer" }}>
          <input type="checkbox" checked={filterUnedited} onChange={(e) => setFilterUnedited(e.target.checked)} style={{ width: "auto" }} />
          仅未编辑
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, cursor: "pointer" }}>
          <input type="checkbox" checked={filterFlagged} onChange={(e) => setFilterFlagged(e.target.checked)} style={{ width: "auto" }} />
          仅待查
        </label>
        <button className="btn btn-sm btn-primary" onClick={handleAllReviewed}>
          全部标记已审
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {entries.map(([name, fieldData]) => {
          const value = typeof fieldData === "object" && fieldData !== null ? fieldData.value : fieldData;
          const edited = typeof fieldData === "object" && fieldData !== null ? fieldData.edited : false;
          const review = reviewData[name] || {};
          const isReviewed = review.reviewed;
          const isFlagged = review.flagged;
          const isUnmentioned = value === "-1" || value === -1;
          const noteVal = localNotes[name] ?? review.note ?? "";

          const cardClass = `review-field ${isReviewed ? "reviewed" : isFlagged ? "flagged" : "pending-review"}`;

          return (
            <div key={name} className={cardClass}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: "var(--text-3)", flex: 1 }}>
                  {name}
                  {edited && <span style={{ color: "var(--primary)", marginLeft: 4 }}>已改</span>}
                </span>
                {isReviewed && <span style={{ color: "var(--success)", fontSize: 11 }}>已审</span>}
                {isFlagged && <span style={{ color: "var(--warning)", fontSize: 11 }}>待查</span>}
              </div>
              <div style={{
                fontSize: 13,
                color: isUnmentioned ? "var(--text-3)" : "var(--text)",
                fontStyle: isUnmentioned ? "italic" : "normal",
                marginBottom: 6,
              }}>
                {isUnmentioned ? "未提及 (-1)" : String(value ?? "")}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button
                  className="btn btn-sm"
                  style={{
                    padding: "3px 8px",
                    borderColor: isReviewed ? "var(--success)" : undefined,
                    color: isReviewed ? "var(--success)" : undefined,
                  }}
                  onClick={() => handleReviewField(name, true)}
                >
                  已审
                </button>
                <button
                  className="btn btn-sm"
                  style={{
                    padding: "3px 8px",
                    borderColor: isFlagged ? "var(--warning)" : undefined,
                    color: isFlagged ? "var(--warning)" : undefined,
                  }}
                  onClick={() => handleReviewField(name, false)}
                >
                  待查
                </button>
                <input
                  value={noteVal}
                  onChange={(e) => handleNoteChange(name, e.target.value)}
                  placeholder="备注…"
                  style={{ fontSize: 11, padding: "3px 6px" }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
