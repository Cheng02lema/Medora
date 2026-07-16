import { useState, useRef, useEffect } from "react";

interface LazyImageProps {
  src: string;
  alt?: string;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  title?: string;
  placeholder?: string; // 占位色
}

/**
 * 懒加载图片：Intersection Observer + 淡入动画 + 错误占位。
 */
export default function LazyImage({
  src,
  alt = "",
  className,
  style,
  onClick,
  title,
  placeholder = "rgba(255,255,255,0.05)",
}: LazyImageProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        ...style,
        background: placeholder,
        overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        position: "relative",
      }}
      onClick={onClick}
      title={title}
    >
      {inView && !error && (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
            opacity: loaded ? 1 : 0,
            transition: "opacity 300ms cubic-bezier(0,0,0.2,1)",
          }}
        />
      )}
      {(!inView || !loaded) && !error && (
        <div
          className="skeleton"
          style={{ width: "100%", height: "100%", position: "absolute", inset: 0 }}
        />
      )}
      {error && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            height: "100%",
            color: "var(--text-3)",
            fontSize: 11,
          }}
        >
          ×
        </div>
      )}
    </div>
  );
}
