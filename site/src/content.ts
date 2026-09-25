/**
 * All site copy and links live here so the marketing site can be edited without
 * touching components. Prices and checkout links are placeholders: set them to
 * your real values (or point checkoutUrl at Stripe / Lemon Squeezy / Gumroad).
 */

export const site = {
  name: "NEXUS",
  tagline: "Your personal AI operating system",
  version: "v0.1",
  repoUrl: "https://github.com/mohnish-cyber/Nexus-ai",
  docsPath: "/docs",
  /** Where "Open app" / "Sign in" send people: a hosted NEXUS frontend, or the local dev server. */
  appUrl: "http://localhost:5173",
  /** Default backend the Status page checks. Visitors can change it on the page. */
  defaultApiUrl: "http://127.0.0.1:8000",
  communityUrl: "", // e.g. a Discord invite. Empty hides the link.
  contactEmail: "", // e.g. "hello@yourdomain.com". Empty hides the link.
  year: 2026,
} as const;

export type NavLink = { label: string; href: string };

export const nav: NavLink[] = [
  { label: "Features", href: "/#features" },
  { label: "Privacy", href: "/#privacy" },
  { label: "Pricing", href: "/pricing" },
  { label: "Docs", href: "/docs" },
  { label: "Status", href: "/status" },
];

export const hero = {
  badge: "Nine specialist agents, one calm interface",
  titleLead: "Talk to your computer.",
  titleAccent: "It talks back, and gets things done.",
  subtitle:
    "NEXUS is a voice-first AI assistant that plans, researches, remembers and acts on your behalf. It reads your documents, runs your routines and, only with your say-so, drives your apps.",
  primaryCta: { label: "Get NEXUS", href: "/pricing" },
  secondaryCta: { label: "Read the docs", href: "/docs" },
  footnote: "Local-first. Bring your own model key, or run fully offline with Ollama.",
};

/** Figures are facts about the product, not vanity metrics. Keep them true. */
export const stats = [
  { value: "9", label: "specialist agents" },
  { value: "100%", label: "local-first by default" },
  { value: "3", label: "permission risk tiers" },
  { value: "< 2 min", label: "from clone to first command" },
];

/** Services NEXUS can plug into. Text only; no third-party logos. */
export const integrations = [
  "Anthropic Claude",
  "Ollama",
  "OpenAI Whisper",
  "ElevenLabs",
  "Tavily",
  "Brave Search",
  "SearXNG",
  "Playwright",
  "Open-Meteo",
  "Supabase",
  "PostgreSQL",
  "SQLite",
];

/** Icon names are lucide-react component names. */
export type Feature = { icon: string; title: string; body: string; tag?: string };

export const features: Feature[] = [
  {
    icon: "Mic",
    title: "Voice, both ways",
    body: "Push-to-talk from the orb, the mic button or Ctrl+Shift+Space. Replies are spoken back with browser, OpenAI or ElevenLabs voices.",
    tag: "Voice",
  },
  {
    icon: "Brain",
    title: "Memory you control",
    body: "Tell it once that your project lives in ~/college/linkguard and “open my project” just works. You approve, edit or delete everything it remembers.",
    tag: "Memory",
  },
  {
    icon: "FileText",
    title: "Study any document",
    body: "Drop in a PDF, DOCX or code file. Heading-aware retrieval answers “explain Unit 3” from Unit 3 only, and keeps your document separate from general knowledge.",
    tag: "Files",
  },
  {
    icon: "Globe",
    title: "Research with sources",
    body: "Searches the web, reads pages safely and answers with citations. Weather works out of the box with no key.",
    tag: "Research",
  },
  {
    icon: "MonitorSmartphone",
    title: "Computer control",
    body: "Launch approved apps, open folders and URLs, run allow-listed dev commands and take screenshots, each behind a permission you can see.",
    tag: "Computer",
  },
  {
    icon: "Code2",
    title: "A careful coding agent",
    body: "Inspect, diagnose, plan, then make the smallest edit, show you the diff, run the tests and verify, all confined to folders you authorise.",
    tag: "Coding",
  },
  {
    icon: "ScanEye",
    title: "It can see your screen",
    body: "Share one frame of your screen or attach an image. NEXUS reads error dialogs, charts and photos and walks you through the fix.",
    tag: "Vision",
  },
  {
    icon: "AlarmClock",
    title: "Routines that run themselves",
    body: "Natural-language reminders, morning news digests, price watches and rain alerts on a scheduler that runs in the background.",
    tag: "Automations",
  },
  {
    icon: "Activity",
    title: "Nothing happens off-screen",
    body: "A live activity feed, agent runs, tool calls and a full audit log. Every reply carries a verified ledger of what was actually done.",
    tag: "Observability",
  },
];

export const privacy = {
  eyebrow: "Privacy guard",
  title: "Powerful by design. Polite by default.",
  body: "Every tool in NEXUS declares a risk level and runs through a single executor that checks arguments, asks permission, enforces a timeout and writes an audit record. Your data stays on your machine unless you choose otherwise.",
  points: [
    {
      icon: "HardDrive",
      title: "Local-first storage",
      body: "Database, files and settings live on your machine in the default mode.",
    },
    {
      icon: "KeyRound",
      title: "Encrypted API keys",
      body: "Keys are stored encrypted, shown once and never sent to the browser.",
    },
    {
      icon: "ShieldCheck",
      title: "Permission-gated actions",
      body: "Medium-risk actions ask first. High-risk actions always ask, every time.",
    },
    {
      icon: "FolderLock",
      title: "Confined file access",
      body: "Only folders you authorise. Credential files are always off-limits.",
    },
    {
      icon: "Network",
      title: "Safe outbound fetches",
      body: "Web requests are guarded against SSRF and page content is treated as untrusted.",
    },
    {
      icon: "ScrollText",
      title: "Full audit trail",
      body: "Every tool call, approval and denial is logged where you can review it.",
    },
  ],
  tiers: [
    { level: "Low", example: "Read, search, open an app", behaviour: "Runs automatically", tone: "ok" },
    { level: "Medium", example: "Edit files, run dev commands", behaviour: "Asks: allow once, always, or cancel", tone: "warn" },
    { level: "High", example: "Delete, install", behaviour: "Always asks. Never auto-allowed", tone: "bad" },
  ],
} as const;

export const steps = [
  {
    title: "Install",
    body: "Clone the repo and run one script. It installs everything and starts NEXUS on your machine.",
    code: "./scripts/dev.sh",
  },
  {
    title: "Connect a model",
    body: "Paste an Anthropic key in Settings, or point NEXUS at a local model through Ollama.",
    code: "AI_PROVIDER=openai_compatible",
  },
  {
    title: "Start talking",
    body: "Press the orb and ask. The boot sequence shows the real status of every subsystem.",
    code: "“What tasks do I have today?”",
  },
];

/** Example requests shown in the "Just ask" section. */
export const commands = [
  { agent: "Memory", text: "My college AI project is LinkGuard AI at ~/college/linkguard." },
  { agent: "Computer", text: "Open my college AI project." },
  { agent: "Tasks", text: "Remind me tomorrow at 8 AM to submit my assignment." },
  { agent: "Research", text: "Check tomorrow's weather and remind me to take an umbrella if it rains." },
  { agent: "Study", text: "Read this PDF and explain Unit 3. Then quiz me on it." },
  { agent: "Vision", text: "What's wrong on my screen? Help me fix it." },
  { agent: "Automation", text: "Every morning at 8, give me five important AI news stories." },
  { agent: "Coding", text: "Run my project's tests and tell me why they fail." },
];

export type Plan = {
  id: "monthly" | "quarterly" | "lifetime";
  name: string;
  price: string;
  period: string;
  blurb: string;
  badge?: string;
  savings?: string;
  highlighted?: boolean;
  cta: string;
  /** Payment link. Empty sends visitors to the install guide instead. */
  checkoutUrl: string;
  features: string[];
};

export const pricing = {
  eyebrow: "Pricing",
  title: "One product. Every agent. Pick how you pay.",
  subtitle:
    "Every plan unlocks the full assistant: all agents, voice, memory, automations and every update. The only difference is how long you're covered.",
  currency: "$",
  plans: [
    {
      id: "monthly",
      name: "Monthly",
      price: "12.99",
      period: "per month",
      blurb: "Try everything with no commitment.",
      cta: "Start monthly",
      checkoutUrl: "",
      features: [
        "All 9 specialist agents",
        "Voice input and spoken replies",
        "Long-term memory with approvals",
        "Document study and quizzes",
        "Reminders and automations",
        "Updates while subscribed",
      ],
    },
    {
      id: "quarterly",
      name: "Quarterly",
      price: "29.99",
      period: "every 3 months",
      blurb: "For people who use it every day.",
      badge: "Most popular",
      savings: "Save 23%",
      highlighted: true,
      cta: "Start quarterly",
      checkoutUrl: "",
      features: [
        "Everything in Monthly",
        "Priority support",
        "Early access to new agents",
        "Updates while subscribed",
      ],
    },
    {
      id: "lifetime",
      name: "Lifetime",
      price: "89",
      period: "one-time payment",
      blurb: "Pay once. Keep every future update.",
      badge: "Best value",
      cta: "Get lifetime",
      checkoutUrl: "",
      features: [
        "Everything in Quarterly",
        "Lifetime updates",
        "No recurring fees, ever",
        "Founding-member role in the community",
      ],
    },
  ] satisfies Plan[],
  included: [
    "Instant access after checkout",
    "Runs on Windows, macOS and Linux",
    "Bring your own model key or run offline",
    "Cancel monthly or quarterly any time",
  ],
  selfHostNote: "Prefer to build it yourself? The source code is on GitHub.",
};

/** Rows for the plan comparison table on /pricing. true / false / or a short string. */
export const comparison: { feature: string; monthly: boolean | string; quarterly: boolean | string; lifetime: boolean | string }[] = [
  { feature: "Research, File, Study, Memory agents", monthly: true, quarterly: true, lifetime: true },
  { feature: "Computer, Coding, Vision agents", monthly: true, quarterly: true, lifetime: true },
  { feature: "Automation and Conversation agents", monthly: true, quarterly: true, lifetime: true },
  { feature: "Push-to-talk and spoken replies", monthly: true, quarterly: true, lifetime: true },
  { feature: "Reminders, digests and price watches", monthly: true, quarterly: true, lifetime: true },
  { feature: "Permission broker and audit log", monthly: true, quarterly: true, lifetime: true },
  { feature: "Product updates", monthly: "While active", quarterly: "While active", lifetime: "Forever" },
  { feature: "Priority support", monthly: false, quarterly: true, lifetime: true },
  { feature: "Early access to new agents", monthly: false, quarterly: true, lifetime: true },
  { feature: "Founding-member community role", monthly: false, quarterly: false, lifetime: true },
];

export const faqs = [
  {
    q: "What exactly is NEXUS?",
    a: "A personal AI assistant that runs on your own computer. You talk or type; NEXUS works out what you want, hands the job to the right specialist agent (research, files, memory, coding and so on) and reports back with a record of what it actually did.",
  },
  {
    q: "Do I need an AI API key?",
    a: "For the full experience, yes: add an Anthropic key in Settings. You can also run a local model through Ollama. Without any model, NEXUS runs in a limited mode where memory, reminders, tasks, app launching, weather and file search still work.",
  },
  {
    q: "Where is my data stored?",
    a: "In the default local mode, everything (database, uploaded files, API keys) stays on your machine. Keys are encrypted at rest and never sent to the browser. An optional multi-user mode uses your own Supabase project with row-level security.",
  },
  {
    q: "Can NEXUS do things on my computer without asking?",
    a: "Only low-risk things like reading, searching or opening an approved app. Editing files or running dev commands asks first, and deleting or installing always asks, with no “always allow” option. Background jobs can never run medium- or high-risk actions.",
  },
  {
    q: "Which platforms are supported?",
    a: "NEXUS needs Python 3.11+ and Node.js 20+, so it runs on Windows, macOS and Linux. The interface works in any modern browser, down to phone width.",
  },
  {
    q: "Does voice work offline?",
    a: "Browser speech recognition and voices work with no extra setup. For server-side transcription you can use OpenAI Whisper or install faster-whisper to run fully offline.",
  },
  {
    q: "Can I cancel or switch plans?",
    a: "Yes. Monthly and quarterly plans can be cancelled any time and stay active until the end of the period you paid for. You can move to Lifetime whenever you like.",
  },
  {
    q: "Is the source code available?",
    a: "Yes. NEXUS is developed in the open on GitHub, so you can read exactly how permissions, memory and every tool work before you trust it with anything.",
  },
];

export const finalCta = {
  title: "Your computer, finally on speaking terms.",
  body: "Set up NEXUS in a couple of minutes and hand off the busywork.",
  primary: { label: "Get NEXUS", href: "/pricing" },
  secondary: { label: "View on GitHub", href: site.repoUrl },
};

export const footer = {
  blurb: "A voice-first, local-first personal AI operating system.",
  columns: [
    {
      title: "Product",
      links: [
        { label: "Features", href: "/#features" },
        { label: "Pricing", href: "/pricing" },
        { label: "Status", href: "/status" },
      ],
    },
    {
      title: "Resources",
      links: [
        { label: "Docs", href: "/docs" },
        { label: "Quick start", href: "/docs#quick-start" },
        { label: "Safety model", href: "/docs#safety" },
      ],
    },
    {
      title: "Project",
      links: [
        { label: "GitHub", href: site.repoUrl },
        { label: "Report an issue", href: `${site.repoUrl}/issues` },
      ],
    },
  ],
  legal: "NEXUS is an independent project. Product names mentioned belong to their respective owners.",
};
