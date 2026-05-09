import { useEffect, useState } from "react";
import { applyTheme, getInitialTheme, Theme } from "../theme";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("light")
      ? "light"
      : document.documentElement.classList.contains("dark")
        ? "dark"
        : getInitialTheme(),
  );

  useEffect(() => {
    const next: Theme = document.documentElement.classList.contains("light") ? "light" : "dark";
    setTheme(next);
  }, []);

  return (
    <div className="theme-toggle" role="group" aria-label="Theme switch">
      <button
        type="button"
        className={theme === "light" ? "is-active" : ""}
        onClick={() => {
          applyTheme("light");
          setTheme("light");
        }}
      >
        Light
      </button>
      <button
        type="button"
        className={theme === "dark" ? "is-active" : ""}
        onClick={() => {
          applyTheme("dark");
          setTheme("dark");
        }}
      >
        Dark
      </button>
    </div>
  );
}
