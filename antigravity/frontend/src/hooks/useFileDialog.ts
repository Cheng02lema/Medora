/**
 * 文件/文件夹选择 Hook。
 *
 * - Electron 环境:使用原生对话框(window.clarinora.selectFolder/selectFile)
 * - Web 环境:回退到手动输入(返回 null,调用方应显示输入框)
 */

export async function selectFolder(): Promise<string | null> {
  // Electron 环境
  if (typeof window !== "undefined" && (window as any).clarinora?.selectFolder) {
    try {
      const path = await (window as any).clarinora.selectFolder();
      return path || null;
    } catch {
      return null;
    }
  }
  // Web 环境:触发隐藏的 webkitdirectory input
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.setAttribute("webkitdirectory", "");
    input.style.display = "none";
    input.onchange = () => {
      if (input.files && input.files.length > 0) {
        // webkitRelativePath 包含目录名
        const path = input.files[0].webkitRelativePath;
        const dir = path.split("/")[0];
        resolve(dir || null);
      } else {
        resolve(null);
      }
    };
    document.body.appendChild(input);
    input.click();
    document.body.removeChild(input);
  });
}

export async function selectFile(filters?: { name: string; extensions: string[] }[]): Promise<string | null> {
  // Electron 环境
  if (typeof window !== "undefined" && (window as any).clarinora?.selectFile) {
    try {
      const path = await (window as any).clarinora.selectFile(filters);
      return path || null;
    } catch {
      return null;
    }
  }
  // Web 环境:触发文件选择器,返回 File 对象的 name(不完整路径)
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    if (filters && filters.length > 0) {
      input.accept = filters[0].extensions.map((e) => "." + e).join(",");
    }
    input.style.display = "none";
    input.onchange = () => {
      if (input.files && input.files.length > 0) {
        resolve(input.files[0].name);
      } else {
        resolve(null);
      }
    };
    document.body.appendChild(input);
    input.click();
    document.body.removeChild(input);
  });
}

export async function selectSaveFile(filters?: { name: string; extensions: string[] }[]): Promise<string | null> {
  // Electron 环境
  if (typeof window !== "undefined" && (window as any).clarinora?.selectSaveFile) {
    try {
      const path = await (window as any).clarinora.selectSaveFile(filters);
      return path || null;
    } catch {
      return null;
    }
  }
  // Web 环境:无法选择保存路径,返回 null
  return null;
}
