// A placeholder until the web app lands (wave 1, slice 3): show that the server answers.
const root = document.getElementById("app");

function say(title, detail) {
  const strong = document.createElement("strong");
  strong.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.className = "boot";
  paragraph.append(strong, detail);
  root.replaceChildren(paragraph);
}

try {
  const response = await fetch("/api/v1/meta");
  const { data } = await response.json();
  document.title = data.product.name;
  say(data.product.name, `${data.product.tagline} Version ${data.version} is running.`);
} catch {
  say("GovWren", "The server is not responding.");
}
