import { createRoot } from "react-dom/client";
import "../panel/panel.css";
import { JournalApp } from "./JournalApp";

createRoot(document.getElementById("root")!).render(<JournalApp />);
