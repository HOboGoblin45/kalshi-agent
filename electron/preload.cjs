const { contextBridge, shell } = require('electron');

contextBridge.exposeInMainWorld('kalshiDesktop', {
  openExternal: (url) => shell.openExternal(url),
  version: process.versions.electron,
});
