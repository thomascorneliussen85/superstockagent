import { createRoot } from "react-dom/client";
import "../panel/panel.css";
import { LiveChartApp } from "./LiveChartApp";

createRoot(document.getElementById("root")!).render(<LiveChartApp />);
