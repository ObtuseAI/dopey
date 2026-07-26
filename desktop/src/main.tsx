import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("DOPEY desktop root element is missing.");
}

const render = (): void => {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
};

if (import.meta.env.DEV) {
  void import("./dev/mockBridge").then(({ installMockBridge }) => {
    installMockBridge();
    render();
  });
} else {
  render();
}
