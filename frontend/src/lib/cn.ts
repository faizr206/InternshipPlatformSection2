import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge our custom token names so overrides like
// `whitespace-normal` or `text-[13px]` on a component win over its defaults.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      rounded: [{ rounded: ["card", "ctl"] }],
      shadow: [{ shadow: ["card", "pop"] }],
    },
  },
});

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
