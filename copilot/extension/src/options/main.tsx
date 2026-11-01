import { createRoot } from "react-dom/client";
import "../panel/panel.css";
import { OptionsPage } from "./OptionsPage";

createRoot(document.getElementById("root")!).render(<OptionsPage />);
