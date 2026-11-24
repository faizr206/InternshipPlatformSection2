import { createContext, useContext } from "react";

export interface UIState {
  openAssistant: (question?: string) => void;
}

export const UICtx = createContext<UIState>({ openAssistant: () => {} });
export const useUI = () => useContext(UICtx);
