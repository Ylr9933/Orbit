import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");

createRoot(root).render(
  <StrictMode>
    <main>
      <p className="stage">S0 · 工程基础</p>
      <h1>Agent Infra</h1>
      <p>围绕 Agent 与 Environment 构建的模块化运行基础设施。</p>
      <p>前端开发入口已就绪。任务执行、资源监控和运行记录将在后续阶段接入。</p>
      <p className="note">此页面不连接业务后端，也不展示模拟运行结果。</p>
    </main>
  </StrictMode>,
);
