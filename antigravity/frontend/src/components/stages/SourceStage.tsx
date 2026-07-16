import { useState, useEffect } from "react";
import { useWorkbench } from "../../store/workbench";
import { api } from "../../api/client";
import LazyImage from "../LazyImage";

export default function SourceStage() {
  const patientDetail = useWorkbench((s) => s.patientDetail);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);

  if (!patientDetail) return null;

  const images = patientDetail.images || [];
  const dataSource = patientDetail.stages?.source?.data?.data_source || "image";

  if (dataSource === "text" || dataSource === "excel") {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">文本 / Excel 数据源</div>
        <div className="empty-desc">
          无源图片。请到「合并」查看文本，或直接「抽取」。
        </div>
      </div>
    );
  }

  if (images.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">·</div>
        <div className="empty-title">该病人文件夹内无图片</div>
        <div className="empty-desc">请确认源目录中包含 jpg/png 等图片文件</div>
      </div>
    );
  }

  const totalSize = images.reduce((sum, img) => sum + img.size, 0);
  const formatSize = (bytes: number) => {
    if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    if (bytes > 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${bytes} B`;
  };

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="h2">源图片 ({images.length} 张, {formatSize(totalSize)})</div>
        <span className="faint">按文件名排序 · 点击查看大图</span>
      </div>

      <div className="image-grid">
        {images.map((img, idx) => (
          <div
            key={img.name}
            className="image-tile"
            onClick={() => setLightboxIdx(idx)}
            style={{ cursor: "pointer" }}
          >
            <LazyImage
              src={api.thumbUrl(patientDetail.id, "source", img.name)}
              alt={img.name}
              style={{ width: "100%", aspectRatio: "3/4", borderRadius: 8 }}
            />
            <div className="page-badge">{idx + 1}</div>
            <div className="tile-overlay">
              <div>
                <div style={{ fontWeight: 600 }}>{img.name}</div>
                <div style={{ color: "var(--text-3)" }}>{formatSize(img.size)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {lightboxIdx !== null && (
        <Lightbox
          images={images}
          current={lightboxIdx}
          patientId={patientDetail.id}
          onClose={() => setLightboxIdx(null)}
          onNavigate={(idx) => setLightboxIdx(idx)}
        />
      )}
    </>
  );
}

function Lightbox({
  images,
  current,
  patientId,
  onClose,
  onNavigate,
}: {
  images: { name: string; size: number }[];
  current: number;
  patientId: string;
  onClose: () => void;
  onNavigate: (idx: number) => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && current > 0) onNavigate(current - 1);
      if (e.key === "ArrowRight" && current < images.length - 1) onNavigate(current + 1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [current, images.length, onClose, onNavigate]);

  return (
    <div className="lightbox" onClick={onClose}>
      <button className="lightbox-close" onClick={onClose}>×</button>
      {current > 0 && (
        <button
          className="lightbox-nav prev"
          onClick={(e) => { e.stopPropagation(); onNavigate(current - 1); }}
        >
          ←
        </button>
      )}
      {current < images.length - 1 && (
        <button
          className="lightbox-nav next"
          onClick={(e) => { e.stopPropagation(); onNavigate(current + 1); }}
        >
          →
        </button>
      )}
      <img
        src={api.imageUrl(patientId, "source", images[current].name)}
        alt={images[current].name}
        onClick={(e) => e.stopPropagation()}
      />
      <div
        style={{
          position: "absolute",
          bottom: 24,
          left: "50%",
          transform: "translateX(-50%)",
          color: "var(--text-2)",
          fontSize: 12,
          background: "rgba(0,0,0,0.6)",
          padding: "6px 12px",
          borderRadius: 6,
        }}
      >
        {current + 1} / {images.length} · {images[current].name}
        <span className="faint" style={{ marginLeft: 12 }}>← → 翻页 · Esc 关闭</span>
      </div>
    </div>
  );
}
