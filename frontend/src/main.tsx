import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#171717", colorBgBase: "#fafafa", colorTextBase: "#171717", borderRadius: 8, fontFamily: 'Inter, ui-sans-serif, system-ui, "Microsoft YaHei", sans-serif' } }}>
      <App />
      <Toaster position="top-center" richColors />
    </ConfigProvider>
  </React.StrictMode>
);
