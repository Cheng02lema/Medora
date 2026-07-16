const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("medora", {
  selectFolder: () => ipcRenderer.invoke("dialog:selectFolder"),
  selectFile: (filters) => ipcRenderer.invoke("dialog:selectFile", filters),
  selectSaveFile: (filters) => ipcRenderer.invoke("dialog:selectSaveFile", filters),
});
