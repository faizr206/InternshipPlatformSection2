import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NAV_ITEMS } from "@/lib/nav";
import { STORAGE_KEY } from "@/context/DemoContext";
import { renderApp } from "./render";

const mainNav = () => screen.getByRole("navigation", { name: "Main" });
const navLabels = () => within(mainNav()).getAllByRole("link").map((a) => a.textContent?.replace(/\d+$/, "").trim());

async function switchRole(label: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("combobox", { name: "Demo as role" }));
  await user.click(await screen.findByRole("option", { name: new RegExp(label) }));
}

describe("demo banner", () => {
  it.each(["/", ...NAV_ITEMS.map((i) => i.path), "/does-not-exist"])("is shown on %s", async (path) => {
    renderApp(path);
    const banner = await screen.findByRole("note", { name: "Demo notice" });
    expect(banner).toHaveTextContent("Synthetic data · simulated roles · demo only");
  });
});

describe("role switcher", () => {
  it("shows the student journey by default", async () => {
    renderApp();
    expect(navLabels()).toEqual([
      "Home", "Profile", "Opportunities", "Applications", "Matching", "Preparation", "Co-op placement", "Assistant",
    ]);
    expect(within(mainNav()).queryByRole("link", { name: /Records/ })).not.toBeInTheDocument();
  });

  it("filters the nav when the role changes and persists the choice", async () => {
    renderApp();
    await switchRole("Workplace supervisor");
    await waitFor(() => expect(navLabels()).toEqual(["Home", "Co-op placement", "Assistant"]));
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).role).toBe("supervisor");

    await switchRole("Coordinator");
    await waitFor(() => expect(navLabels()).toContain("Records"));
    expect(navLabels()).toContain("Opportunities");
  });

  it("sends you home when the new role can't see the current page", async () => {
    renderApp("/matching");
    expect(await screen.findByRole("heading", { level: 1, name: "Matching" })).toBeInTheDocument();
    await switchRole("Employer");
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
  });

  it("shows count badges from the API", async () => {
    renderApp();
    const matching = within(mainNav()).getByRole("link", { name: /Matching/ });
    expect(await within(matching).findByLabelText("3 pending")).toBeInTheDocument();
  });
});

describe("pages", () => {
  it("renders the role-aware home with journey, to-dos and activity", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ role: "coordinator", studentId: "COOP-B001" }));
    renderApp();
    expect(await screen.findByRole("list", { name: "Layla Hassan's journey" })).toBeInTheDocument();
    expect(await screen.findByText("Review employer submissions")).toBeInTheDocument();
    expect(await screen.findByText(/approved and published/)).toBeInTheDocument();
    expect(screen.getByText(/Welcome back, Dr. Salma/)).toBeInTheDocument();
  });

  it("shows the owner chip on module placeholders", async () => {
    renderApp("/applications");
    const header = (await screen.findByRole("heading", { level: 1, name: "Applications" })).parentElement!;
    expect(within(header).getByText("P04")).toBeInTheDocument();
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("answers from the FAQ in the assistant drawer", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getAllByRole("button", { name: /assistant/i })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Assistant" });
    await user.type(within(dialog).getByLabelText("Your question"), "Are placements on site?{Enter}");
    expect(await within(dialog).findByText(/remote roles are not approved/)).toBeInTheDocument();
  });
});
