import { useEffect, useRef, useState } from "react";

interface UseDraftOptions {
  key: string;          // localStorage key
  initialValue: string;
  debounceMs?: number;  // 自动保存延迟
}

/**
 * 编辑草稿自动保存到 localStorage。
 *
 * - 输入变化后 debounceMs 自动保存
 * - 返回 hasDraft 标记（有未提交的草稿）
 * - clearDraft() 清除草稿
 */
export function useDraft({ key, initialValue, debounceMs = 2000 }: UseDraftOptions) {
  const [value, setValue] = useState(initialValue);
  const [hasDraft, setHasDraft] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialized = useRef(false);

  // 加载草稿
  useEffect(() => {
    const saved = localStorage.getItem(key);
    if (saved && saved !== initialValue) {
      setValue(saved);
      setHasDraft(true);
    }
    initialized.current = true;
  }, [key]);

  // 自动保存
  useEffect(() => {
    if (!initialized.current) return;
    if (value === initialValue) {
      setHasDraft(false);
      localStorage.removeItem(key);
      return;
    }
    setHasDraft(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      localStorage.setItem(key, value);
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value, key, initialValue, debounceMs]);

  const clearDraft = () => {
    localStorage.removeItem(key);
    setHasDraft(false);
    setValue(initialValue);
  };

  return { value, setValue, hasDraft, clearDraft };
}
