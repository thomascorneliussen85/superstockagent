import { createRoot } from "react-dom/client";
import "../panel/panel.css";
import { ReplayApp } from "./ReplayApp";

createRoot(document.getElementById("root")!).render(<ReplayApp />);
