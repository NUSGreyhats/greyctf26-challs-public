import type { StageSlug } from "./types";

export const POLL_INTERVAL_MS = 500;

export const stageOrder: StageSlug[] = ["pinpoint", "queens", "tango"];

export const stageMeta: Record<
  StageSlug,
  {
    index: 1 | 2 | 3;
    title: string;
    path: string;
    shortDescription: string;
    modalBody: string[];
  }
> = {
  pinpoint: {
    index: 1,
    title: "Pinpoint",
    path: "/play/pinpoint",
    shortDescription: "Enter my brain, guess the word!",
    modalBody: ["Guess the hidden word", "You have 5 guesses"],
  },
  queens: {
    index: 2,
    title: "Queens",
    path: "/play/queens",
    shortDescription: "How many queens can we really fit?",
    modalBody: [
      "Each board may have at most one queen in each row and column",
      "To win, you must successfully place 1337 queens",
    ],
  },
  tango: {
    index: 3,
    title: "Tango",
    path: "/play/tango",
    shortDescription: "Solve the puzzle enough times, buy the flag.",
    modalBody: [
      "Complete every blank tile as sun or moon",
      "Rows and columns need balanced symbols",
      "Accepted plays settle as $100 awarded and $100 play cost",
      "Refresh Ledger settles pending credits and can lower spendable balance",
    ],
  },
};
