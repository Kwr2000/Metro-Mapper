import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

const icon = document.createElement("link");
icon.rel = "icon";
icon.href = "favicon.svg";
document.head.append(icon);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
