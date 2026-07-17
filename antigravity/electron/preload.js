const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("clarinora", {
  selectFolder: () => ipcRenderer.invoke("dialog:selectFolder"),
  selectFile: (filters) => ipcRenderer.invoke("dialog:selectFile", filters),
  selectSaveFile: (filters) => ipcRenderer.invoke("dialog:selectSaveFile", filters),
});
