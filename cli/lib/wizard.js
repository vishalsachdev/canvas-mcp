import prompts from "prompts";
import { clients } from "./clients.js";

async function runWizard() {
  console.log("\n  Canvas MCP Setup\n");

  const response = await prompts(
    [
      {
        type: "password",
        name: "token",
        message: "Enter your Canvas API token:",
        validate: (v) => (v.length > 0 ? true : "Token is required"),
      },
      {
        type: "text",
        name: "canvasUrl",
        message: "Enter your Canvas URL (e.g., https://canvas.illinois.edu):",
        validate: (v) => {
          try {
            const url = new URL(v);
            return url.protocol === "https:" ? true : "URL must start with https://";
          } catch {
            return "Enter a valid URL";
          }
        },
      },
      {
        type: "multiselect",
        name: "selectedClients",
        message: "Which client(s) to configure?",
        choices: clients.map((c) => ({ title: c.name, value: c.id })),
        min: 1,
        hint: "- Space to select, Enter to confirm",
      },
    ],
    {
      onCancel: () => {
        console.log("\nSetup cancelled.");
        process.exit(0);
      },
    }
  );

  return {
    token: response.token,
    canvasUrl: response.canvasUrl.replace(/\/+$/, ""),
    selectedClients: response.selectedClients,
  };
}

export { runWizard };
