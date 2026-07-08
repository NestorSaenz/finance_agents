import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ChatInput } from "./ChatInput";

function Harness({ disabled = false, onSend }: { disabled?: boolean; onSend?: () => void }) {
  const [value, setValue] = useState("");
  return (
    <ChatInput
      value={value}
      onChange={setValue}
      onSend={onSend ?? (() => {})}
      disabled={disabled}
      imageName={null}
      imagePreview={null}
      attachError={null}
      onAttach={() => {}}
      onClearImage={() => {}}
    />
  );
}

describe("ChatInput", () => {
  it("sends on Enter and clears is left to the parent", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);

    await userEvent.type(screen.getByRole("textbox"), "gasté 50{Enter}");

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("does NOT send on Shift+Enter (newline instead)", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);

    await userEvent.type(screen.getByRole("textbox"), "línea 1{Shift>}{Enter}{/Shift}línea 2");

    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveValue("línea 1\nlínea 2");
  });

  it("disables the send button when empty and enables it after typing", async () => {
    render(<Harness />);
    const button = screen.getByRole("button", { name: "Enviar mensaje" });
    expect(button).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox"), "hola");

    expect(button).toBeEnabled();
  });

  it("enables send with an attached image even when the text is empty", () => {
    render(
      <ChatInput
        value=""
        onChange={() => {}}
        onSend={() => {}}
        disabled={false}
        imageName="excel.png"
        imagePreview={null}
        attachError={null}
        onAttach={() => {}}
        onClearImage={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Enviar mensaje" })).toBeEnabled();
    expect(screen.getByText("excel.png")).toBeInTheDocument();
  });

  it("does not send when disabled (in flight)", async () => {
    const onSend = vi.fn();
    render(<Harness disabled onSend={onSend} />);

    await userEvent.type(screen.getByRole("textbox"), "hola{Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });
});
