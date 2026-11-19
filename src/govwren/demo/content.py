"""What the fictional institute is made of: its units, the names its people are drawn from,
its vendors and tools, and the kinds of things its people ask to do with AI.

Everything here is invented. Nothing is taken from a real organization, and the vendor and
product names are made up.
"""

from __future__ import annotations

from typing import Any

ORGANIZATION = "Alderpoint Institute for Medical Research"
DOMAIN = "alderpoint.example"

# --- Units ----------------------------------------------------------------------------------

# Research divisions, with a code, how many labs each has, and what its labs work on.
DIVISIONS: list[tuple[str, str, int, list[str]]] = [
    ("Cancer Biology", "CAN", 7,
     ["tumor sequencing", "organoid imaging", "drug-response screen", "single-cell RNA", "histology"]),
    ("Immunology and Infectious Disease", "IMM", 7,
     ["flow cytometry", "antibody repertoire", "vaccine-response", "T-cell receptor", "pathogen genomics"]),
    ("Neuroscience", "NEU", 7,
     ["electrophysiology", "calcium imaging", "behavioral video", "brain MRI", "connectomics"]),
    ("Population Health", "POP", 6,
     ["cohort survey", "disease registry", "insurance claims", "environmental exposure", "wearable sensor"]),
    ("Computational Biology", "CMP", 7,
     ["protein structure", "variant calling", "multi-omics", "gene-regulation", "benchmarking"]),
    ("Clinical Research", "CLN", 6,
     ["trial enrollment", "adverse-event", "visit-note", "consent-form", "study protocol"]),
]  # fmt: skip

CORES: list[tuple[str, str]] = [
    ("Genomics Core", "GEN"),
    ("Imaging Core", "IMG"),
    ("Biostatistics Core", "BST"),
    ("Proteomics Core", "PRT"),
    ("Research Computing", "RCP"),
]

OFFICES: list[tuple[str, str]] = [
    ("Information Technology", "IT"),
    ("Research Integrity", "RIO"),
    ("Privacy Office", "PRV"),
    ("Legal", "LGL"),
    ("Human Resources", "HR"),
    ("Finance", "FIN"),
    ("Communications", "COM"),
    ("Library", "LIB"),
    ("Education and Training", "EDU"),
]

# Units inside Information Technology, so that the tree goes four deep on the administrative
# side as well as the research side.
IT_TEAMS: list[tuple[str, str]] = [("Service Desk", "ITSD"), ("Information Security", "ITSEC")]

# --- People ---------------------------------------------------------------------------------

GIVEN = """Aaliyah Abena Adaeze Akira Alejandro Amara Anders Anika Arjun Astrid Beatriz Bongani
Camila Carmen Chidi Chloe Daniel Darius Deepa Dmitri Elena Elif Emeka Esther Fatima Felix
Gabriela Grace Hana Haruto Hassan Helga Ibrahim Imani Ingrid Isabel Ivan Jamal Jelena Jin
Jorge Kavya Keiko Kofi Lars Layla Leila Liam Lin Lucia Malik Marcus Maren Mateo Mei Miriam
Nadia Naoki Nia Nikolai Noor Oluwaseun Omar Paloma Pedro Quinn Rahul Rania Rosa Sana Sanjay
Selin Sipho Sofia Soren Tariq Tessa Thandiwe Theo Uma Valentina Viktor Wanjiru Xavier Yara
Yusuf Zainab Zofia""".split()

FAMILY = """Abdi Achterberg Adeyemi Aguilar Akhtar Almeida Andersson Arce Asante Bakker Balogun
Banerjee Baptiste Bekele Bianchi Bjork Brandt Castellanos Chaudhry Cisneros Dalgaard Dlamini
Dubois Eklund Espinoza Farouk Ferreira Fischer Fontaine Gallo Gashi Gunawardena Haddad
Halvorsen Hashemi Hoang Idowu Ilves Iyer Jankowski Jaramillo Kallio Kamara Karimi Kowalczyk
Kuznetsov Lachance Lemaire Lindahl Lombardi Madaki Mahlangu Marchetti Mbeki Meyerhoff Mokoena
Montero Moreau Mwangi Nakamura Ndlovu Nilsen Novak Nwosu Obuya Okonkwo Olawale Oyelaran
Paredes Pellegrini Petrov Quispe Rahimi Ramaswamy Rasmussen Rautio Restrepo Rojas Saarinen
Sandoval Sato Sepulveda Shrestha Siddiqui Sokolov Sorensen Takahashi Tanaka Tembo Thorsen
Tshabalala Uchida Valdivia Varga Vasquez Venter Wachira Watanabe Wekesa Yilmaz Zamora
Zielinski Zubiri""".split()

LAB_TITLES = [
    ("Staff Scientist", 2),
    ("Postdoctoral Fellow", 3),
    ("Graduate Student", 3),
    ("Research Technician", 2),
    ("Lab Manager", 1),
    ("Data Analyst", 1),
]

OFFICE_TITLES = {
    "IT": ["Systems Engineer", "Applications Developer", "IT Project Manager"],
    "ITSD": ["Service Desk Lead", "Service Desk Analyst", "Service Desk Analyst"],
    "ITSEC": ["Security Engineer", "Security Analyst"],
    "RIO": ["Research Integrity Officer", "Compliance Analyst"],
    "PRV": ["Privacy Analyst", "Privacy Analyst"],
    "LGL": ["Associate General Counsel", "Contracts Manager", "Paralegal"],
    "HR": ["Talent Acquisition Lead", "HR Business Partner", "Benefits Specialist"],
    "FIN": ["Grants Accountant", "Accounts Payable Lead", "Financial Analyst"],
    "COM": ["Science Writer", "Digital Content Manager", "Media Relations Lead"],
    "LIB": ["Research Librarian", "Data Services Librarian"],
    "EDU": ["Training Program Manager", "Instructional Designer"],
}

CORE_TITLES = ["Core Manager", "Senior Research Associate", "Research Associate", "Analyst"]

# The people every build has, whatever the seed, so that the guides can name them.
# (key, name, title, unit code, role, review function, what the sign-in page says)
CAST: list[tuple[str, str, str, str, str, str | None, str]] = [
    ("admin", "Dana Okafor", "Systems Administrator", "IT", "admin", None,
     "Administrator: people, units, and appearance"),
    ("governance", "Sam Reyes", "Director of AI Governance", "RIO", "governance", None,
     "Governance lead: triage, decisions, the catalog, and the dashboard"),
    ("deputy", "Amara Lindqvist", "AI Governance Analyst", "RIO", "governance", None,
     "Governance analyst: shares the queue with the lead"),
    ("privacy", "Wei Chen", "Privacy Officer", "PRV", "reviewer", "privacy",
     "Reviewer for privacy"),
    ("security", "Ines Duarte", "Information Security Lead", "ITSEC", "reviewer", "security",
     "Reviewer for security"),
    ("auditor", "Ruth Abara", "Internal Auditor", "FIN", "auditor", None,
     "Auditor: reads everything, changes nothing"),
    ("division", "Henrik Solberg", "Director, Neuroscience", "NEU", "steward", None,
     "Steward of the Neuroscience division"),
    ("pi", "Priya Nair", "Principal Investigator", "NEU-NAIR", "steward", None,
     "Principal investigator and steward of the Nair Lab"),
    ("member", "Tomas Lind", "Postdoctoral Fellow", "NEU-HALE", "member", None,
     "Researcher in the Hale Lab: asks, registers, and answers questions"),
]  # fmt: skip

# Two labs that exist in every build because members of the cast work in them.
FIXED_LABS = {"NEU": [("Nair", "Priya Nair"), ("Hale", "Marguerite Hale")]}

# One reviewer for each remaining function: (function, name, title, unit code)
REVIEWERS: list[tuple[str, str, str, str]] = [
    ("privacy", "Callum Adair", "Senior Privacy Analyst", "PRV"),
    ("security", "Noura Haidari", "Security Architect", "ITSEC"),
    ("legal", "Margit Olander", "Deputy General Counsel", "LGL"),
    ("ethics", "Obinna Eze", "Director, Human Research Protection", "RIO"),
    ("integrity", "Lorena Ibarra", "Research Integrity Lead", "RIO"),
    ("clinical_safety", "Dr. Anneke Visser", "Medical Director, Clinical Research Unit", "CRU"),
    ("data_stewardship", "Kwabena Osei", "Research Data Steward", "LIB"),
    ("architecture", "Mirela Dragan", "Enterprise Architect", "IT"),
]

# --- Vendors and tools ----------------------------------------------------------------------

# (name, standing, due diligence, a line about them)
VENDORS: list[tuple[str, str, str, str]] = [
    ("Brightfen Labs", "active", "complete", "General-purpose AI assistants and model services."),
    ("Quillstream", "active", "complete", "Consumer chat and transcription apps."),
    ("Harborlight Software", "active", "complete", "Office suite with built-in AI features."),
    ("Orrery AI", "active", "complete", "Research assistants for literature and data."),
    ("Anvilworks", "active", "complete", "AI coding tools for software teams."),
    ("Tidewick Labs", "prospective", "in_progress", "Code completion for scientific computing."),
    ("Larkspur Audio", "active", "complete", "Speech-to-text for meetings and interviews."),
    ("Meetmoor", "active", "in_progress", "Meeting notes and action items."),
    ("Citefinch", "active", "complete", "Literature search and citation checking."),
    ("Paperglass", "active", "in_progress", "Manuscript drafting and editing."),
    ("Segmentry Bio", "active", "complete", "Image segmentation for microscopy."),
    ("Veridale Health AI", "active", "complete", "Clinical documentation and summarization."),
    ("Trialwick", "active", "in_progress", "Trial matching and feasibility."),
    ("Cobaltine Compute", "active", "complete", "Hosted inference for open-weight models."),
    ("Deskhand", "active", "complete", "Service-desk automation."),
    ("Kestrel Works", "active", "complete", "Laboratory scheduling and inventory."),
    ("Marlowe Analytics", "active", "complete", "Statistical software with AI assistance."),
    ("Northfell Genomics", "active", "complete", "Sequencing instruments and analysis software."),
    ("Osprey Vale", "prospective", "not_started", "Grant discovery and proposal support."),
    ("Pinemoor Data", "active", "in_progress", "Data de-identification services."),
    ("Quorrel Bioinformatics", "active", "complete", "Variant interpretation."),
    ("Redwillow", "active", "complete", "Recruiting and applicant tracking."),
    ("Saltmarsh Labs", "prospective", "in_progress", "Autonomous lab-notebook agents."),
    ("Thistle & Finch", "active", "complete", "Translation and plain-language rewriting."),
    ("Umbrel Vision", "active", "in_progress", "Radiology image analysis."),
    ("Vantmoor Proteomics", "active", "complete", "Mass-spectrometry analysis software."),
    ("Willowbank", "active", "complete", "Finance and accounts-payable automation."),
    ("Yarrow Health", "offboarding", "complete", "Patient-reported outcome collection."),
    ("Zephyrine", "active", "complete", "Image and illustration generation."),
    ("Junco Cloud", "active", "complete", "Cloud platform with managed AI services."),
    ("Halden Speech", "former", "complete", "Dictation software, replaced in the last year."),
    ("Greywether", "active", "in_progress", "Contract review for legal teams."),
    ("Foxmere Insights", "prospective", "not_started", "Survey analysis and text coding."),
    ("Emberline", "active", "complete", "Learning platform with a tutoring assistant."),
    ("Driftwood AI", "prospective", "not_started", "Agents for literature review."),
    ("Corvine Labs", "active", "in_progress", "Security log analysis."),
    ("Bellmoor Sciences", "active", "complete", "Electronic lab notebook."),
    ("Ashgrove Informatics", "active", "complete", "Clinical trial management system."),
    ("Stonechat Systems", "active", "complete", "Help-center chatbots."),
    ("Wrenfield Robotics", "prospective", "not_started", "Automated sample handling."),
]

TERMS_GENERAL = (
    "Sign in with your work account. Do not enter identifiable participant or patient "
    "information. Check every output before relying on it. Say when AI helped write "
    "something that will be published."
)
TERMS_CODE = (
    "Do not paste credentials, keys, or tokens. Review and test suggested code as you would "
    "a colleague's. Do not accept suggestions into code that handles Restricted data without "
    "a second reviewer."
)
TERMS_SPEECH = (
    "Tell everyone present before recording. Do not record participants in a study unless "
    "the protocol allows it. Delete recordings once the notes are checked."
)
TERMS_PUBLIC = (
    "Public information only. The supplier may train on what you enter, so do not enter "
    "anything you would not post on the institute's website."
)

# Tools the governance office has evaluated.
# (name, vendor, kind, edition, hosting, access, summary, standing, data class, excluded,
#  trains on inputs, terms)
CATALOG: list[tuple[Any, ...]] = [
    ("Brightfen Assistant", "Brightfen Labs", "vendor_product", "Enterprise", "vendor", "web",
     "A general-purpose chat assistant for drafting, summarizing, and coding help.",
     "approved", "protected", ["health", "export_controlled", "credentials"], "no", TERMS_GENERAL),
    ("Brightfen Assistant", "Brightfen Labs", "vendor_product", "Free", "vendor", "web",
     "The free edition of the chat assistant, signed in with a personal account.",
     "approved_with_restrictions", "public", [], "yes", TERMS_PUBLIC),
    ("Brightfen API", "Brightfen Labs", "model_service", "Enterprise", "vendor", "api",
     "Programmatic access to Brightfen's language models under the institute's agreement.",
     "approved", "protected", ["health", "credentials"], "no", TERMS_GENERAL),
    ("Harborlight Copilot", "Harborlight Software", "embedded_feature", "Institute license",
     "vendor", "embedded",
     "AI features inside the institute's email, documents, and spreadsheets.",
     "approved", "protected", ["export_controlled"], "no", TERMS_GENERAL),
    ("Orrery Research Assistant", "Orrery AI", "vendor_product", "Team", "vendor", "web",
     "Finds and summarizes papers, with every claim linked to its source.",
     "approved", "internal", ["health", "genetic"], "no", TERMS_GENERAL),
    ("Anvilworks Code", "Anvilworks", "vendor_product", "Business", "vendor", "plugin",
     "Code completion and chat inside the editor.",
     "approved", "internal", ["credentials", "health"], "no", TERMS_CODE),
    ("Larkspur Scribe", "Larkspur Audio", "vendor_product", "Enterprise", "vendor", "desktop",
     "Transcribes meetings and interviews on the institute's tenant.",
     "approved", "protected", ["genetic"], "no", TERMS_SPEECH),
    ("Meetmoor Notes", "Meetmoor", "vendor_product", "Business", "vendor", "plugin",
     "Joins video meetings and writes notes and action items.",
     "approved_with_restrictions", "internal", ["health", "human_subjects", "personal"], "no",
     TERMS_SPEECH),
    ("Citefinch", "Citefinch", "vendor_product", "Institution", "vendor", "web",
     "Literature search that checks whether cited papers say what they are cited for.",
     "approved", "public", [], "no", "Check every reference it returns against the paper."),
    ("Paperglass Editor", "Paperglass", "vendor_product", "Team", "vendor", "web",
     "Edits manuscript text for clarity and journal style.",
     "approved_with_restrictions", "internal", ["health", "human_subjects"], "unknown",
     "Unpublished results may be entered. Do not use it on manuscripts you are refereeing. "
     "Disclose its use where the journal asks."),
    ("Segmentry Cell", "Segmentry Bio", "vendor_product", "On-premises", "on_premises", "desktop",
     "Segments cells and nuclei in microscopy images on the lab's own workstation.",
     "approved", "protected", [], "no",
     "Check segmentation on a sample of images from each new experiment before trusting counts."),
    ("Veridale Visit Summaries", "Veridale Health AI", "vendor_product", "Clinical research",
     "vendor", "embedded",
     "Drafts a summary of each study visit from the coordinator's notes.",
     "approved_with_restrictions", "restricted", ["genetic"], "no",
     "Only within an approved use case. A coordinator reads and signs every summary."),
    ("Cobaltine Inference", "Cobaltine Compute", "model_service", "Dedicated", "vendor", "api",
     "Runs open-weight models on dedicated machines in one region.",
     "approved", "protected", ["health"], "no", TERMS_GENERAL),
    ("Deskhand Agent", "Deskhand", "agent", "Enterprise", "vendor", "embedded",
     "Reads incoming service-desk tickets, suggests a category, and can resolve simple ones.",
     "approved_with_restrictions", "internal", ["health", "credentials"], "no",
     "Only within an approved use case. It may close only the ticket types on its allow-list."),
    ("Kestrel Booker", "Kestrel Works", "agent", "Core facilities", "vendor", "web",
     "Books instrument time and reorders consumables when asked.",
     "approved", "internal", [], "no", "Orders above the unit's limit need a person's approval."),
    ("Marlowe Stat Assistant", "Marlowe Analytics", "embedded_feature", "Site license",
     "on_premises", "desktop",
     "Suggests models and writes analysis code inside the statistics package.",
     "approved", "restricted", [], "no",
     "Runs on your own machine. A statistician reviews any analysis plan it proposes."),
    ("Northfell Basecaller", "Northfell Genomics", "embedded_feature", "Instrument software",
     "on_premises", "embedded",
     "The neural basecaller that ships with the sequencers.",
     "approved", "restricted", [], "no", "Record the model version with every run."),
    ("Quorrel Interpret", "Quorrel Bioinformatics", "vendor_product", "Research", "vendor", "web",
     "Suggests a classification for genetic variants with the supporting evidence.",
     "approved_with_restrictions", "restricted", [], "no",
     "Research use only. Not for returning results to participants."),
    ("Thistle & Finch Translate", "Thistle & Finch", "vendor_product", "Business", "vendor", "web",
     "Translation and plain-language rewriting.",
     "approved", "internal", ["health"], "no",
     "Have a fluent speaker check anything given to participants or the public."),
    ("Vantmoor Rescore", "Vantmoor Proteomics", "embedded_feature", "Core license",
     "on_premises", "desktop",
     "Rescores peptide identifications with a learned model.",
     "approved", "protected", [], "no", "Record the model version with every search."),
    ("Willowbank Coding Suggestions", "Willowbank", "embedded_feature", "Finance suite",
     "vendor", "embedded",
     "Suggests account codes for invoices.",
     "approved", "internal", [], "no", "A person approves every coded invoice."),
    ("Zephyrine Studio", "Zephyrine", "vendor_product", "Team", "vendor", "web",
     "Generates illustrations from a description.",
     "approved_with_restrictions", "public", [], "yes",
     "Not for scientific figures or images of real people. Label generated images."),
    ("Junco AI Services", "Junco Cloud", "model_service", "Institute tenant", "own_cloud", "api",
     "Managed language and vision models inside the institute's own cloud tenant.",
     "approved", "restricted", ["export_controlled"], "no",
     "Use the institute's tenant only. Restricted data needs an approved use case."),
    ("Emberline Tutor", "Emberline", "embedded_feature", "Campus", "vendor", "embedded",
     "A tutoring assistant inside the learning platform.",
     "approved", "internal", ["health"], "no",
     "Tell learners when an answer came from the assistant."),
    ("Bellmoor Notebook Assistant", "Bellmoor Sciences", "embedded_feature", "Institute",
     "vendor", "embedded",
     "Searches and summarizes entries in the electronic lab notebook.",
     "approved", "protected", ["health"], "no", TERMS_GENERAL),
    ("Stonechat Helper", "Stonechat Systems", "vendor_product", "Standard", "vendor", "embedded",
     "A chatbot for the staff help center that answers from published policies.",
     "approved", "internal", ["health", "personal"], "no",
     "Answers must link to the policy they come from."),
    ("Corvine Log Insight", "Corvine Labs", "vendor_product", "Enterprise", "vendor", "web",
     "Summarizes security logs and suggests where to look.",
     "approved_with_restrictions", "protected", ["health"], "no",
     "Information Security staff only. An analyst confirms every finding."),
    ("Greywether Review", "Greywether", "vendor_product", "Legal", "vendor", "web",
     "First-pass comparison of an agreement against the institute's standard terms.",
     "approved_with_restrictions", "protected", ["health"], "no",
     "Legal staff only. Counsel reads every agreement in full."),
    ("Pinemoor Scrub", "Pinemoor Data", "vendor_product", "On-premises", "on_premises", "api",
     "Removes names, dates, and other identifiers from free text.",
     "approved", "restricted", [], "no",
     "Check a sample of every batch. De-identified text is still Protected until confirmed."),
    ("Redwillow Match", "Redwillow", "embedded_feature", "Recruiting suite", "vendor", "embedded",
     "Ranks job applicants against the posting.",
     "not_approved", None, [], "unknown", None),
    ("Quillstream Chat", "Quillstream", "vendor_product", "Consumer", "vendor", "web",
     "A consumer chat app.",
     "not_approved", None, [], "yes", None),
    ("Quillstream Transcribe", "Quillstream", "vendor_product", "Consumer", "vendor", "web",
     "A consumer transcription app that keeps recordings to improve its models.",
     "not_approved", None, [], "yes", None),
    ("Halden Dictate", "Halden Speech", "vendor_product", "Desktop", "local", "desktop",
     "Dictation software that the institute has stopped licensing.",
     "not_approved", None, [], "unknown", None),
    ("Tidewick Autocomplete", "Tidewick Labs", "vendor_product", "Research preview", "vendor",
     "plugin", "Code completion trained on scientific software.",
     "under_evaluation", None, [], "unknown", None),
    ("Trialwick Navigator", "Trialwick", "vendor_product", "Pilot", "vendor", "web",
     "Suggests open trials a patient may be eligible for.",
     "under_evaluation", None, [], "no", None),
    ("Umbrel Read", "Umbrel Vision", "vendor_product", "Research", "vendor", "web",
     "Outlines lesions on research MRI scans.",
     "under_evaluation", None, [], "no", None),
    ("Saltmarsh Notebook Agent", "Saltmarsh Labs", "agent", "Beta", "vendor", "web",
     "An agent that plans and records routine analyses in a lab notebook.",
     "under_evaluation", None, [], "unknown", None),
    ("Osprey Vale Grants", "Osprey Vale", "vendor_product", "Institution", "vendor", "web",
     "Finds funding calls and drafts sections of proposals.",
     "under_evaluation", None, [], "unknown", None),
    ("Foxmere Coder", "Foxmere Insights", "vendor_product", "Team", "vendor", "web",
     "Codes free-text survey answers into themes.",
     "under_evaluation", None, [], "unknown", None),
    ("Driftwood Reviewer", "Driftwood AI", "agent", "Beta", "vendor", "web",
     "An agent that searches the literature and drafts a review.",
     "under_evaluation", None, [], "unknown", None),
]  # fmt: skip

# Tools that people in the labs added themselves: nobody has evaluated them.
# (name, kind, hosting, access, summary)
UNLISTED: list[tuple[str, str, str, str, str]] = [
    (
        "Open-weight language model on the lab workstation",
        "open_source",
        "local",
        "desktop",
        "A small open-weight language model run with a local runner. Nothing leaves the machine.",
    ),
    (
        "Protein language model embeddings",
        "open_source",
        "on_premises",
        "api",
        "An open protein language model on the cluster, used for sequence embeddings.",
    ),
    (
        "Cell-type classifier (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "A classifier trained in the lab on its own annotated single-cell data.",
    ),
    (
        "Spike-sorting network",
        "open_source",
        "local",
        "desktop",
        "An open-source neural spike sorter.",
    ),
    (
        "Pose-estimation toolkit",
        "open_source",
        "local",
        "desktop",
        "Tracks animal posture in behavioral video.",
    ),
    (
        "Histology tile classifier (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "Classifies tissue regions in slide images. Trained on the lab's own slides.",
    ),
    (
        "Variant effect predictor",
        "open_source",
        "on_premises",
        "api",
        "An open model that scores the likely effect of missense variants.",
    ),
    (
        "Structure prediction pipeline",
        "open_source",
        "on_premises",
        "api",
        "Open-weight structure prediction run on the cluster's GPU nodes.",
    ),
    (
        "Speech-to-text model on the cluster",
        "open_source",
        "on_premises",
        "api",
        "An open speech recognition model run on the institute's own hardware.",
    ),
    (
        "Lab chatbot over protocols (in-house)",
        "internal_app",
        "own_cloud",
        "web",
        "A small app that answers questions from the lab's protocol documents.",
    ),
    (
        "Survey topic model",
        "open_source",
        "local",
        "desktop",
        "Topic modeling of free-text survey answers.",
    ),
    (
        "Denoising network for calcium imaging",
        "open_source",
        "local",
        "desktop",
        "A self-supervised denoiser for imaging movies.",
    ),
    (
        "Image restoration model for light-sheet data",
        "open_source",
        "on_premises",
        "desktop",
        "A content-aware restoration model trained on paired images.",
    ),
    (
        "Risk score for hospital readmission (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "A gradient-boosted model built by the biostatistics core on registry data.",
    ),
    (
        "Genome language model",
        "open_source",
        "on_premises",
        "api",
        "An open DNA language model used to score regulatory variants.",
    ),
    (
        "Mass-spectrum predictor",
        "open_source",
        "on_premises",
        "api",
        "Predicts fragment spectra for peptide candidates.",
    ),
    (
        "Literature alert summarizer (in-house)",
        "internal_app",
        "own_cloud",
        "api",
        "A script that summarizes each week's new papers for the lab.",
    ),
    (
        "Chat plugin in the reference manager",
        "embedded_feature",
        "vendor",
        "plugin",
        "An AI panel that appeared in the reference manager after an update.",
    ),
    (
        "AI features in the plate-reader software",
        "embedded_feature",
        "local",
        "embedded",
        "Curve fitting suggestions that came with the instrument's latest software.",
    ),
    (
        "AI search in the video-conferencing app",
        "embedded_feature",
        "vendor",
        "embedded",
        "Summaries and search across recorded meetings, turned on by the supplier.",
    ),
    (
        "Free image upscaler",
        "vendor_product",
        "vendor",
        "web",
        "A free website that enlarges images.",
    ),
    (
        "Browser extension that rewrites text",
        "vendor_product",
        "vendor",
        "plugin",
        "A grammar and tone extension that sends page text to its supplier.",
    ),
    (
        "Slide-deck generator",
        "vendor_product",
        "vendor",
        "web",
        "Makes presentation slides from an outline.",
    ),
    (
        "Diagram generator",
        "vendor_product",
        "vendor",
        "web",
        "Draws pathway diagrams from a text description.",
    ),
    (
        "Notebook coding assistant",
        "embedded_feature",
        "vendor",
        "embedded",
        "The AI helper inside the hosted notebook service.",
    ),
    (
        "Adverse-event text classifier (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "Flags narrative reports that may describe a serious adverse event.",
    ),
    (
        "Eligibility pre-screener (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "Ranks records for manual eligibility review against a study's criteria.",
    ),
    (
        "Wearable signal classifier (in-house)",
        "internal_app",
        "own_cloud",
        "api",
        "Classifies sleep stages from wrist-worn sensor data.",
    ),
    (
        "Phishing classifier in the mail gateway",
        "embedded_feature",
        "vendor",
        "embedded",
        "The supplier's model that scores inbound mail.",
    ),
    (
        "Resume keyword screener",
        "embedded_feature",
        "vendor",
        "embedded",
        "A screening feature in the applicant tracking system.",
    ),
    (
        "Expense anomaly detector",
        "embedded_feature",
        "vendor",
        "embedded",
        "Flags unusual expense reports for a second look.",
    ),
    (
        "Repository metadata tagger (in-house)",
        "internal_app",
        "own_cloud",
        "api",
        "Suggests subject headings for items in the institutional repository.",
    ),
    (
        "Figure-integrity screener",
        "vendor_product",
        "vendor",
        "web",
        "Looks for duplicated or altered regions in figures.",
    ),
    (
        "Quiz-question generator",
        "vendor_product",
        "vendor",
        "web",
        "Drafts quiz questions from course material.",
    ),
    (
        "Cluster help assistant (in-house)",
        "internal_app",
        "on_premises",
        "web",
        "Answers questions from the research computing documentation.",
    ),
    (
        "Radiology report language model",
        "open_source",
        "on_premises",
        "api",
        "An open clinical language model fine-tuned in-house on de-identified reports.",
    ),
    (
        "Lab inventory reorder agent (in-house)",
        "agent",
        "own_cloud",
        "api",
        "A script that watches stock levels and drafts orders.",
    ),
    (
        "Primer design assistant",
        "vendor_product",
        "vendor",
        "web",
        "Suggests primers and guide RNAs.",
    ),
    (
        "Microscope autofocus network",
        "embedded_feature",
        "local",
        "embedded",
        "Learned autofocus shipped with the microscope's software.",
    ),
    (
        "Flow-cytometry gating model",
        "open_source",
        "local",
        "desktop",
        "Automated gating trained on manually gated samples.",
    ),
    (
        "Antibody developability predictor",
        "open_source",
        "on_premises",
        "api",
        "Scores antibody sequences for likely stability problems.",
    ),
    (
        "Epidemic forecasting ensemble (in-house)",
        "internal_app",
        "own_cloud",
        "api",
        "Combines several forecasting models for the weekly outlook.",
    ),
    (
        "Geocoding and exposure linkage model",
        "internal_app",
        "on_premises",
        "api",
        "Links addresses to exposure estimates.",
    ),
    (
        "Consent-form readability checker",
        "vendor_product",
        "vendor",
        "web",
        "Scores reading level and suggests simpler wording.",
    ),
    (
        "Protocol deviation classifier (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "Sorts deviation reports by type.",
    ),
    (
        "Speaker-diarization model",
        "open_source",
        "local",
        "desktop",
        "Separates speakers in a recording.",
    ),
    (
        "Connectome proofreading agent",
        "agent",
        "on_premises",
        "api",
        "Proposes merges and splits in a reconstruction for a person to accept.",
    ),
    (
        "Drug-response predictor (in-house)",
        "internal_app",
        "on_premises",
        "api",
        "Predicts response from expression profiles of cell lines.",
    ),
    (
        "Grant-budget checker",
        "vendor_product",
        "vendor",
        "web",
        "Checks a budget justification against the sponsor's rules.",
    ),
    (
        "Alt-text generator",
        "vendor_product",
        "vendor",
        "plugin",
        "Writes image descriptions for web pages.",
    ),
    (
        "Meeting translator",
        "vendor_product",
        "vendor",
        "plugin",
        "Live captions and translation in video meetings.",
    ),
    (
        "Email triage rules with AI",
        "embedded_feature",
        "vendor",
        "embedded",
        "Sorts and drafts replies in the mail client.",
    ),
    (
        "Cryo-EM particle picker",
        "open_source",
        "on_premises",
        "desktop",
        "A learned particle picker.",
    ),
    (
        "Chemical structure recognizer",
        "open_source",
        "local",
        "desktop",
        "Reads structures from figures in papers.",
    ),
    (
        "Pathology foundation model",
        "open_source",
        "on_premises",
        "api",
        "An open-weight vision model for slide images, used for embeddings.",
    ),
]

# --- What people ask to do ------------------------------------------------------------------

# Answer sets by the kind of use. Each is merged over BASE.
BASE: dict[str, Any] = {
    "stage": "in_use",
    "domain": "research",
    "affected_groups": ["team"],
    "impact": "none",
    "decision_role": "exploratory",
    "autonomy": "output_only",
    "human_oversight": "A member of the team reads each output before it is used.",
    "outputs_used_for": ["analysis"],
    "data_class": "internal",
    "data_categories": [],
    "exposure": "vendor_agreement",
    "reach": "team",
    "trains_on_inputs": "no",
}

PROFILES: dict[str, dict[str, Any]] = {
    # Everyday work with an approved tool: registered from the catalog.
    "everyday": {},
    "minimal": {"outputs_used_for": ["analysis"]},
    "writing": {
        "outputs_used_for": ["publications"], "data_categories": ["unpublished"],
        "decision_role": "informs",
        "human_oversight": "The authors rewrite and check every passage and every reference.",
    },
    "grants": {
        "outputs_used_for": ["grant_applications"], "data_categories": ["unpublished"],
        "decision_role": "informs", "reach": "one_unit",
        "human_oversight": "The principal investigator edits and signs off on every section.",
    },
    "code": {
        "domain": "software", "outputs_used_for": ["production_software"],
        "data_categories": ["source_code"], "decision_role": "informs",
        "human_oversight": "Every change is reviewed and tested before it is merged.",
    },
    "local": {
        "exposure": "own_equipment", "data_class": "protected",
        "data_categories": ["unpublished"], "decision_role": "informs",
        "human_oversight": "Results are spot-checked against manual analysis for every batch.",
    },
    "moderate": {
        "data_class": "protected", "reach": "one_unit", "decision_role": "informs",
        "data_categories": ["unpublished"],
        "human_oversight": "A scientist reviews flagged items and a sample of the rest.",
    },
    "people_data": {
        "data_class": "protected", "data_categories": ["personal", "human_subjects"],
        "affected_groups": ["participants"], "decision_role": "informs", "impact": "minor",
        "reach": "one_unit",
        "human_oversight": "A study coordinator checks every output against the source.",
    },
    "health": {
        "domain": "clinical", "data_class": "restricted",
        "data_categories": ["health", "human_subjects", "personal"],
        "affected_groups": ["participants"], "decision_role": "informs",
        "impact": "significant", "reach": "one_unit",
        "human_oversight": "A coordinator reads every output, and a clinician reviews a sample.",
    },
    "clinical": {
        "domain": "clinical", "data_class": "restricted",
        "data_categories": ["health", "human_subjects", "personal"],
        "affected_groups": ["patients", "participants"], "decision_role": "recommends",
        "impact": "serious", "reach": "many_units",
        "human_oversight": "A clinician reviews every recommendation before anything is done.",
    },
    "genomic": {
        "data_class": "restricted", "data_categories": ["genetic", "human_subjects", "under_agreement"],
        "affected_groups": ["participants"], "decision_role": "informs", "impact": "minor",
        "exposure": "own_equipment", "reach": "one_unit",
        "human_oversight": "Calls are confirmed by a second method before they are reported.",
    },
    "agent": {
        "domain": "operations", "autonomy": "acts_within_limits", "decision_role": "recommends",
        "affected_groups": ["staff"], "impact": "minor", "reach": "org_wide",
        "data_categories": ["personal"], "outputs_used_for": [],
        "human_oversight": "Staff see everything it does and can reverse any action.",
    },
    "assistant_agent": {
        "domain": "operations", "autonomy": "acts_with_approval", "decision_role": "informs",
        "affected_groups": ["staff"], "reach": "one_unit", "outputs_used_for": [],
        "human_oversight": "It proposes; a person approves each action.",
    },
    "staff_decisions": {
        "domain": "operations", "decision_role": "recommends", "impact": "significant",
        "affected_groups": ["staff", "public"], "data_class": "protected",
        "data_categories": ["personal"], "outputs_used_for": ["decisions_about_people"],
        "reach": "org_wide",
        "human_oversight": "A recruiter reviews every application the tool ranks low.",
    },
    "operations": {
        "domain": "operations", "decision_role": "informs", "affected_groups": ["staff"],
        "reach": "one_unit", "outputs_used_for": ["communications"],
        "human_oversight": "The responsible member of staff approves every output.",
    },
    "finance": {
        "domain": "operations", "decision_role": "recommends", "affected_groups": ["staff"],
        "data_class": "protected", "reach": "one_unit", "outputs_used_for": [],
        "human_oversight": "An accountant approves every suggestion before it is posted.",
    },
    "education": {
        "domain": "education", "decision_role": "informs", "affected_groups": ["students"],
        "reach": "one_unit", "outputs_used_for": ["communications"],
        "human_oversight": "The instructor reviews what the assistant tells learners each week.",
    },
    "public": {
        "domain": "operations", "data_class": "public", "affected_groups": ["public"],
        "decision_role": "informs", "reach": "org_wide", "outputs_used_for": ["communications"],
        "human_oversight": "An editor approves everything before it is published.",
    },
    # Things the policy does not allow.
    "stop_consumer": {
        "data_class": "restricted", "data_categories": ["human_subjects", "personal"],
        "affected_groups": ["participants"], "exposure": "vendor_no_agreement",
        "trains_on_inputs": "yes", "decision_role": "informs", "impact": "minor",
        "human_oversight": "The interviewer would correct each transcript.",
    },
    "stop_peer_review": {
        "outputs_used_for": ["peer_review"], "data_categories": ["unpublished"],
        "decision_role": "informs", "exposure": "vendor_no_agreement",
        "trains_on_inputs": "unknown",
        "human_oversight": "The referee would rewrite the report.",
    },
}  # fmt: skip

# What research labs ask for. {topic} is filled from the division's work.
# (name, what it is for, profile, tools that suit it)
RESEARCH_USES: list[tuple[str, str, str, list[str]]] = [
    (
        "Summarizing lab meeting notes",
        "Turn each week's notes into a summary with decisions and action items.",
        "everyday",
        ["Brightfen Assistant", "Harborlight Copilot", "Meetmoor Notes"],
    ),
    (
        "Summarizing {topic} results for collaborators",
        "Draft a plain summary of new {topic} results to send to collaborating groups.",
        "everyday",
        ["Brightfen Assistant", "Harborlight Copilot"],
    ),
    (
        "Transcribing recorded lab seminars",
        "Transcribe internal seminars so that people who missed them can search what was said.",
        "everyday",
        ["Larkspur Scribe"],
    ),
    (
        "Translating protocols for visiting researchers",
        "Translate bench protocols for visitors, checked by a fluent member of the lab.",
        "everyday",
        ["Thistle & Finch Translate"],
    ),
    (
        "Summarizing lab protocols with a model on the cluster",
        "Ask questions of the lab's own protocols with an open-weight model the institute runs.",
        "everyday",
        ["Wrenlet 70B", "Wrenlet 7B"],
    ),
    (
        "Transcribing lab recordings on our own hardware",
        "Transcribe recorded lab meetings with an open speech model run on the cluster.",
        "everyday",
        ["Tern Speech Large"],
    ),
    (
        "Finding and summarizing papers on {topic} methods",
        "Search the literature on {topic} methods and summarize what each paper found.",
        "everyday",
        ["Orrery Research Assistant", "Citefinch"],
    ),
    (
        "Checking references in drafts",
        "Check that the papers a draft cites say what the draft says they do.",
        "everyday",
        ["Citefinch"],
    ),
    (
        "Searching the lab notebook",
        "Ask questions of the lab's notebook entries and get an answer with links to them.",
        "everyday",
        ["Bellmoor Notebook Assistant"],
    ),
    (
        "Drafting and polishing manuscript text",
        "Improve the clarity of manuscript drafts about the lab's {topic} work.",
        "writing",
        ["Paperglass Editor", "Brightfen Assistant"],
    ),
    (
        "Drafting responses to reviewer comments",
        "Draft point-by-point responses to referees for the authors to rewrite.",
        "writing",
        ["Brightfen Assistant"],
    ),
    (
        "Drafting specific aims for grant applications",
        "Draft and tighten the aims page and background for funding applications.",
        "grants",
        ["Brightfen Assistant", "Harborlight Copilot"],
    ),
    (
        "Writing analysis scripts for {topic} data",
        "Write and explain scripts that process the lab's {topic} data.",
        "code",
        ["Anvilworks Code", "Brightfen Assistant"],
    ),
    (
        "Code review assistance for the {topic} pipeline",
        "Suggest fixes and tests for the pipeline that processes {topic} data.",
        "code",
        ["Anvilworks Code"],
    ),
    (
        "Segmenting cells in {topic} images",
        "Outline cells and nuclei in {topic} images so that they can be counted and measured.",
        "local",
        ["Segmentry Cell"],
    ),
    (
        "Quality-control flags for {topic} runs",
        "Flag {topic} runs whose quality measures look unusual, for a scientist to check.",
        "local",
        [],
    ),
    (
        "Classifying {topic} samples with a model trained in the lab",
        "Assign a class to each {topic} sample using a model the lab trained on its own data.",
        "local",
        [],
    ),
    (
        "Asking questions of lab protocols with a local model",
        "Run an open-weight language model on a lab workstation to answer from protocol files.",
        "local",
        [],
    ),
    (
        "Predicting outcomes from {topic} data",
        "Train and apply a model that predicts an outcome of interest from {topic} data.",
        "moderate",
        ["Junco AI Services", "Cobaltine Inference"],
    ),
    (
        "Embedding {topic} records for similarity search",
        "Compute embeddings of {topic} records to find similar ones across experiments.",
        "moderate",
        ["Cobaltine Inference", "Junco AI Services", "Brightfen API"],
    ),
    (
        "Extracting methods details from published papers",
        "Pull reagents, doses, and settings from methods sections into a table.",
        "minimal",
        ["Brightfen API", "Orrery Research Assistant"],
    ),
    (
        "Generating figure captions and alt text",
        "Draft captions and image descriptions for figures, edited by the authors.",
        "minimal",
        ["Brightfen Assistant"],
    ),
    (
        "Designing primers and guides with an AI assistant",
        "Suggest primer and guide sequences, each checked against the reference genome.",
        "minimal",
        [],
    ),
    (
        "Classifying variants from {topic} data",
        "Suggest a classification for variants found in {topic} studies under a data use agreement.",
        "genomic",
        ["Quorrel Interpret", "Northfell Basecaller"],
    ),
]

# What groups working with people's data ask for.
HUMAN_USES: list[tuple[str, str, str, list[str]]] = [
    (
        "Coding free-text answers in the {topic} study",
        "Assign themes to free-text answers in the {topic} study, checked by two coders.",
        "people_data",
        ["Brightfen API", "Junco AI Services"],
    ),
    (
        "Drafting plain-language summaries of consent forms",
        "Draft a short plain-language summary of each consent form for the ethics committee.",
        "people_data",
        ["Thistle & Finch Translate", "Brightfen Assistant"],
    ),
    (
        "Transcribing participant interviews",
        "Transcribe recorded interviews with study participants for qualitative analysis.",
        "people_data",
        ["Larkspur Scribe"],
    ),
    (
        "Removing identifiers from {topic} documents",
        "Strip names, dates, and other identifiers from {topic} documents before analysis.",
        "health",
        ["Pinemoor Scrub"],
    ),
    (
        "Summarizing {topic} documents for coordinators",
        "Draft a summary of each {topic} document for the study coordinator to check and sign.",
        "health",
        ["Veridale Visit Summaries", "Junco AI Services"],
    ),
    (
        "Screening records for eligibility in {topic} studies",
        "Rank records for manual eligibility review against the criteria of {topic} studies.",
        "clinical",
        ["Junco AI Services"],
    ),
    (
        "Flagging possible serious adverse events",
        "Flag narrative reports that may describe a serious adverse event for urgent review.",
        "clinical",
        [],
    ),
    (
        "Linking {topic} records across sources",
        "Match records about the same person across {topic} sources using a learned matcher.",
        "health",
        ["Junco AI Services"],
    ),
]

# What the cores and offices ask for, by unit code.
UNIT_USES: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "GEN": [
        (
            "Basecalling and variant filtering with neural models",
            "Use the sequencers' neural basecaller and a learned filter for every run.",
            "genomic",
            ["Northfell Basecaller"],
        ),
        (
            "Answering users' questions about sequencing options",
            "Draft replies to common questions from labs about library preparation and depth.",
            "everyday",
            ["Brightfen Assistant"],
        ),
    ],
    "IMG": [
        (
            "Automated cell segmentation for core users",
            "Offer segmentation as a service on images acquired in the core.",
            "local",
            ["Segmentry Cell"],
        ),
        (
            "Image restoration for low-light acquisitions",
            "Restore low-signal images with a learned model, keeping the raw data alongside.",
            "local",
            [],
        ),
    ],
    "BST": [
        (
            "Drafting statistical analysis plans",
            "Draft analysis plans from a study outline for a statistician to rewrite.",
            "moderate",
            ["Marlowe Stat Assistant"],
        ),
        (
            "Summarizing consulting sessions",
            "Summarize each consulting session and the advice given.",
            "everyday",
            ["Harborlight Copilot"],
        ),
        (
            "Readmission risk model for a registry study",
            "Develop and validate a model of readmission risk on registry data.",
            "health",
            ["Marlowe Stat Assistant"],
        ),
    ],
    "PRT": [
        (
            "Rescoring peptide identifications",
            "Rescore search results with a learned model to increase identifications.",
            "local",
            ["Vantmoor Rescore"],
        ),
    ],
    "RCP": [
        (
            "Answering cluster questions from the documentation",
            "A help assistant that answers users' questions from the cluster documentation.",
            "operations",
            ["Brightfen API", "Stonechat Helper"],
        ),
        (
            "Hosting open-weight language models for labs",
            "Run a small set of open-weight language models on the cluster for any lab to use.",
            "moderate",
            [],
        ),
        (
            "Booking instrument time with an agent",
            "Let an agent book and rearrange instrument time when users ask it to.",
            "assistant_agent",
            ["Kestrel Booker"],
        ),
    ],
    "IT": [
        (
            "Code completion for internal applications",
            "Use an AI coding assistant when building and maintaining internal applications.",
            "code",
            ["Anvilworks Code"],
        ),
        (
            "Drafting knowledge-base articles",
            "Draft how-to articles from resolved tickets, edited before they are published.",
            "everyday",
            ["Harborlight Copilot", "Brightfen Assistant"],
        ),
    ],
    "ITSD": [
        (
            "Suggested replies for service-desk analysts",
            "Suggest a reply to each ticket for the analyst to edit and send.",
            "operations",
            ["Deskhand Agent", "Harborlight Copilot"],
        ),
    ],
    "ITSEC": [
        (
            "Summarizing security logs during investigations",
            "Summarize log extracts and suggest where to look next during an investigation.",
            "moderate",
            ["Corvine Log Insight"],
        ),
        (
            "Scoring inbound mail for phishing",
            "Use the mail gateway's model to score and quarantine suspicious messages.",
            "agent",
            [],
        ),
    ],
    "RIO": [
        (
            "Screening submitted figures for image-integrity problems",
            "Screen figures in manuscripts for duplicated or altered regions before submission.",
            "moderate",
            [],
        ),
        (
            "Summarizing policy questions from researchers",
            "Summarize the questions researchers send in, to find where guidance is unclear.",
            "everyday",
            ["Harborlight Copilot"],
        ),
    ],
    "PRV": [
        (
            "Summarizing privacy incident reports",
            "Draft a summary of each incident report for the privacy officer.",
            "moderate",
            ["Harborlight Copilot"],
        ),
    ],
    "LGL": [
        (
            "First-pass review of data use agreements",
            "Compare incoming agreements with the institute's standard terms and list differences.",
            "moderate",
            ["Greywether Review"],
        ),
        (
            "Summarizing sponsor terms in award notices",
            "Summarize the terms of each new award for the research administrator.",
            "minimal",
            ["Greywether Review", "Harborlight Copilot"],
        ),
    ],
    "HR": [
        (
            "Ranking job applicants against the posting",
            "Rank applications against the minimum qualifications for recruiters to review.",
            "staff_decisions",
            ["Redwillow Match"],
        ),
        (
            "Drafting job descriptions",
            "Draft job descriptions from a hiring manager's notes.",
            "everyday",
            ["Harborlight Copilot", "Brightfen Assistant"],
        ),
        (
            "Answering benefits questions with a help-center chatbot",
            "A chatbot that answers staff questions from the published benefits policies.",
            "operations",
            ["Stonechat Helper"],
        ),
    ],
    "FIN": [
        (
            "Suggesting account codes for invoices",
            "Suggest an account code for each invoice for an accountant to approve.",
            "finance",
            ["Willowbank Coding Suggestions"],
        ),
        (
            "Flagging unusual expense reports",
            "Flag expense reports that look unusual for a second look.",
            "finance",
            [],
        ),
    ],
    "COM": [
        (
            "Drafting news stories about published research",
            "Draft news stories from published papers, checked with the authors.",
            "public",
            ["Brightfen Assistant"],
        ),
        (
            "Generating illustrations for event materials",
            "Generate decorative illustrations for posters and event pages.",
            "public",
            ["Zephyrine Studio"],
        ),
        (
            "Writing image descriptions for the website",
            "Draft alt text for images on the public website.",
            "public",
            ["Brightfen Assistant"],
        ),
    ],
    "LIB": [
        (
            "Answering reference questions with a research assistant",
            "Use a research assistant to find sources when answering reference questions.",
            "everyday",
            ["Orrery Research Assistant", "Citefinch"],
        ),
        (
            "Suggesting subject headings for repository items",
            "Suggest subject headings for new items, approved by a librarian.",
            "minimal",
            ["Brightfen API"],
        ),
    ],
    "EDU": [
        (
            "Tutoring assistant for the biostatistics short course",
            "A tutoring assistant that answers learners' questions from the course material.",
            "education",
            ["Emberline Tutor"],
        ),
        (
            "Drafting quiz questions from course material",
            "Draft quiz questions for instructors to edit.",
            "education",
            ["Emberline Tutor", "Brightfen Assistant"],
        ),
    ],
    "CRU": [
        (
            "Drafting visit reminders in plain language",
            "Draft reminder messages for study visits, approved by the coordinator.",
            "people_data",
            ["Thistle & Finch Translate"],
        ),
    ],
}

# --- What reviewers and requesters say ------------------------------------------------------

QUESTIONS = [
    (
        "Which fields from the source records will be entered, and are any of them free text?",
        "Only the fields listed in the data section. Two are free text; we strip names and dates "
        "from those before anything is entered.",
    ),
    (
        "Who checks the output before it is used, and how is that recorded?",
        "The person named as accountable owner checks it and initials the entry in the lab "
        "notebook. We have added that to our procedure.",
    ),
    (
        "Does the supplier keep what is entered, and for how long?",
        "The agreement says inputs are kept for thirty days for abuse monitoring and then "
        "deleted. I have attached the reference.",
    ),
    (
        "Is this covered by the current ethics protocol, or does it need an amendment?",
        "The protocol allows computational analysis of the recordings. We have asked the ethics "
        "office to confirm that it covers this tool.",
    ),
    (
        "What happens if the tool is unavailable or wrong: is there a manual fallback?",
        "Yes. The manual process stays in place, and we compare the two on a sample each month.",
    ),
    (
        "Will results from this be reported outside the team?",
        "Only in aggregate, and only after the checks described under oversight.",
    ),
]

NOTES = {
    "privacy": [
        "The data described is consistent with the protocol. Identifiers are removed before entry.",
        "Minimum necessary is met. Retention by the supplier is within the agreement.",
        "Acceptable if identifiers are removed first; see the recommended condition.",
    ],
    "security": [
        "Single sign-on is enforced and the tenant is restricted to institute accounts.",
        "The supplier's assurance report is current. No concerns with the integration.",
        "Service account permissions should be reduced to the minimum before it goes live.",
    ],
    "legal": [
        "The agreement in place covers this use. No changes are needed.",
        "The data use agreement permits this analysis on institute systems only.",
        "The supplier's terms need the confidentiality addendum before Restricted data is used.",
    ],
    "ethics": [
        "The protocol covers this analysis. No amendment is needed.",
        "An amendment is needed to name the tool; see the recommended condition.",
    ],
    "integrity": [
        "Consistent with the authorship and disclosure policy, with the standard conditions.",
        "Authors remain responsible for every statement and reference. No concerns.",
    ],
    "clinical_safety": [
        "Nothing here reaches a patient without a clinician's review. Acceptable.",
        "A clinician must confirm each output before it is acted on; see the condition.",
    ],
    "data_stewardship": [
        "The dataset's terms allow this use. Provenance is recorded.",
    ],
    "architecture": [
        "Fits the integration pattern. The agent's permissions are scoped to its allow-list.",
        "Acceptable once the stop control has been tested; see the recommended condition.",
    ],
}

RATIONALES = {
    "approved": [
        "The use is proportionate to its risk and the safeguards described are adequate.",
        "Reviewers found no concerns. Approved for the purpose and data described.",
        "The oversight described is appropriate for the tier. Approved.",
    ],
    "conditions": [
        "Approved on the conditions below, which reflect the reviewers' findings.",
        "The reviewers' recommendations are adopted as conditions. Approved on those terms.",
        "Approved for the purpose described. The conditions below must be met as stated.",
    ],
    "declined": [
        "The data involved may not be used with a tool that has no covering agreement. "
        "An approved alternative exists in the catalog.",
        "The benefit described does not justify the risk to the people affected.",
        "The oversight described would not catch errors before they affect people.",
    ],
    "returned": [
        "Please say which approved tool will be used, and confirm that identifiers are removed "
        "before anything is entered.",
        "Please describe how outputs are checked before use, and by whom.",
        "The data section and the description do not agree. Please correct whichever is wrong.",
    ],
}

CONDITION_NOTES = [
    "Done, and recorded in the lab's procedure.",
    "Completed and confirmed with the reviewer.",
    "In place since the start of use.",
    "Confirmed by the unit's steward.",
]

# --- Models ---------------------------------------------------------------------------------

# Models from suppliers, reached as a service.
# (name, vendor, kind, family, version, modality, withdrawn in days from today or None,
#  the catalog tools built on it, summary)
SUPPLIER_MODELS: list[tuple[Any, ...]] = [
    ("Brightfen Large 4", "Brightfen Labs", "language", "Brightfen Large", "4", ["text", "code", "image"], None,
     ["Brightfen Assistant", "Brightfen API"], "Brightfen's largest general-purpose model."),
    ("Brightfen Small 4", "Brightfen Labs", "language", "Brightfen Small", "4", ["text", "code"], None,
     ["Brightfen API", "Stonechat Helper"], "A smaller, faster model for routine tasks."),
    ("Brightfen Large 3", "Brightfen Labs", "language", "Brightfen Large", "3", ["text", "code"], 45,
     ["Harborlight Copilot", "Bellmoor Notebook Assistant", "Thistle & Finch Translate"],
     "The previous generation. The supplier is withdrawing it."),
    ("Brightfen Embed 2", "Brightfen Labs", "embedding", "Brightfen Embed", "2", ["text"], None,
     ["Brightfen API", "Orrery Research Assistant"], "Text embeddings for search."),
    ("Orrery Reader 2", "Orrery AI", "language", "Orrery Reader", "2", ["text"], None,
     ["Orrery Research Assistant", "Citefinch"], "Tuned by the supplier for reading papers."),
    ("Anvilworks Coder 6", "Anvilworks", "language", "Anvilworks Coder", "6", ["code"], None,
     ["Anvilworks Code"], "A code model."),
    ("Larkspur Speech 3", "Larkspur Audio", "speech", "Larkspur Speech", "3", ["audio"], None,
     ["Larkspur Scribe", "Meetmoor Notes"], "Speech recognition with speaker labels."),
    ("Veridale Clinical S", "Veridale Health AI", "language", "Veridale Clinical", "S-2", ["text"], None,
     ["Veridale Visit Summaries"], "A language model tuned by the supplier on clinical text."),
    ("Deskhand Planner 2", "Deskhand", "language", "Deskhand Planner", "2", ["text"], None,
     ["Deskhand Agent"], "Plans and carries out service-desk actions."),
    ("Zephyrine Image 5", "Zephyrine", "vision", "Zephyrine Image", "5", ["image"], None,
     ["Zephyrine Studio"], "Generates images from text."),
    ("Greywether Clause 1", "Greywether", "language", "Greywether Clause", "1", ["text"], None,
     ["Greywether Review"], "Compares contract clauses."),
    ("Quillstream Q-7", "Quillstream", "language", "Quillstream Q", "7", ["text", "audio"], None,
     ["Quillstream Chat", "Quillstream Transcribe"], "The model behind the consumer apps."),
]  # fmt: skip

# Open weights the institute runs itself.
# (name, made by, kind, family, version, modality, license, restrictions, format, size,
#  catalog standing, data class it may be used with, summary)
OPEN_MODELS: list[tuple[Any, ...]] = [
    ("Wrenlet 7B", "Open Models Collective", "language", "Wrenlet", "1.2", ["text", "code"], "Apache-2.0", None,
     "safetensors", "7 billion parameters", "approved", "restricted",
     "A small general-purpose language model that runs on one GPU."),
    ("Wrenlet 70B", "Open Models Collective", "language", "Wrenlet", "1.2", ["text", "code"], "Apache-2.0", None,
     "safetensors", "70 billion parameters", "approved", "restricted",
     "The large Wrenlet. Runs on the cluster's GPU nodes."),
    ("Kestrel Code 15B", "Kestrel Research", "language", "Kestrel Code", "2.0", ["code"], "MIT", None,
     "gguf", "15 billion parameters", "approved", "protected", "An open code model."),
    ("Aspen Embed", "Aspen Lab", "embedding", "Aspen", "v3", ["text"], "Apache-2.0", None,
     "safetensors", "335 million parameters", "approved", "restricted", "Text embeddings for search."),
    ("Tern Speech Large", "Tern Audio Group", "speech", "Tern Speech", "large-v2", ["audio"], "MIT", None,
     "safetensors", "1.5 billion parameters", "approved", "restricted",
     "Speech recognition that runs on the institute's own hardware."),
    ("Helix Protein LM", "Helix Consortium", "scientific", "Helix", "650M", ["sequence"], "MIT", None,
     "safetensors", "650 million parameters", "approved", "protected", "A protein language model."),
    ("Fathom DNA LM", "Fathom Genomics Lab", "scientific", "Fathom", "2.5B", ["sequence"],
     "Research-only license", "No commercial use. No use on data from identifiable people without consent.",
     "pickle", "2.5 billion parameters", "approved_with_restrictions", "protected", "A DNA language model."),
    ("Osprey Vision Base", "Osprey Vision Group", "vision", "Osprey", "base-16", ["image"], "Apache-2.0", None,
     "safetensors", "86 million parameters", "approved", "restricted", "A general vision backbone."),
    ("Marten Segmenter", "Marten Imaging Lab", "vision", "Marten", "2.1", ["image"], "BSD-3-Clause", None,
     "onnx", "40 million parameters", "approved", "restricted", "Segments cells in microscopy images."),
    ("Pathway Slide Encoder", "Pathway Histology Group", "vision", "Pathway", "1.0", ["image"],
     "Non-commercial research license", "No commercial use. No redistribution of weights.",
     "pickle", "300 million parameters", "approved_with_restrictions", "restricted",
     "A vision model for whole-slide images, used for embeddings."),
    ("Clinical Notes LM", "Open Clinical Language Group", "language", "ClinNotes", "base", ["text"],
     "Credentialed-access license", "Access needs a signed data use agreement with the source.",
     "safetensors", "110 million parameters", "under_evaluation", None,
     "A language model pre-trained on de-identified clinical notes."),
    ("Murmur Diarizer", "Murmur Speech Lab", "speech", "Murmur", "3.1", ["audio"], "MIT", None,
     "safetensors", "20 million parameters", "approved", "restricted", "Separates speakers in a recording."),
    ("Structura Fold", "Structura Group", "scientific", "Structura", "2.3", ["sequence"], "Apache-2.0", None,
     "pickle", "93 million parameters", "approved", "protected", "Predicts protein structure."),
    ("Quoll 3B", "Quoll Project", "language", "Quoll", "3B-instruct", ["text"],
     "Community license", "Acceptable-use terms forbid some uses. Read them before deploying.",
     "gguf", "3 billion parameters", "not_approved", None,
     "A small model whose license was judged too uncertain."),
]  # fmt: skip

# Models a lab builds or tunes itself. {topic} is the lab's work.
# (name, kind, origin, tuning method, base open model or None, modality, summary)
LAB_MODELS: list[tuple[str, str, str, str | None, str | None, list[str], str]] = [
    (
        "{Topic} classifier",
        "classical",
        "in_house",
        None,
        None,
        ["tabular"],
        "A gradient-boosted classifier trained on the lab's own {topic} data.",
    ),
    (
        "{Topic} notes model",
        "language",
        "fine_tuned",
        "adapter",
        "Wrenlet 7B",
        ["text"],
        "Wrenlet 7B with adapters trained on the lab's {topic} notes.",
    ),
    (
        "{Topic} segmentation model",
        "vision",
        "fine_tuned",
        "full",
        "Marten Segmenter",
        ["image"],
        "The open segmenter, fine-tuned on the lab's annotated {topic} images.",
    ),
    (
        "{Topic} embedding model",
        "scientific",
        "fine_tuned",
        "head",
        "Helix Protein LM",
        ["sequence"],
        "A new head on a frozen protein language model, for the lab's {topic} work.",
    ),
    (
        "{Topic} outcome predictor",
        "classical",
        "in_house",
        None,
        None,
        ["tabular", "signal"],
        "Predicts an outcome of interest from {topic} data.",
    ),
    (
        "{Topic} image encoder",
        "vision",
        "fine_tuned",
        "adapter",
        "Osprey Vision Base",
        ["image"],
        "The open vision backbone, adapted to the lab's {topic} images.",
    ),
]

# --- Datasets -------------------------------------------------------------------------------

# (name, data class, kinds of data, who it is about, identifiability, how identifiers were
#  removed, where it came from, what it may not be used for)
LAB_DATASETS: list[tuple[Any, ...]] = [
    (
        "{Topic} raw data",
        "internal",
        ["unpublished"],
        [],
        "not_about_people",
        None,
        "Generated in the lab.",
        None,
    ),
    (
        "{Topic} annotated training set",
        "protected",
        ["unpublished"],
        [],
        "not_about_people",
        None,
        "Annotated by members of the lab over several years.",
        "Not to be shared before publication.",
    ),
    (
        "Public {topic} benchmark",
        "public",
        [],
        [],
        "not_about_people",
        None,
        "Downloaded from a public repository.",
        None,
    ),
]
HUMAN_DATASETS: list[tuple[Any, ...]] = [
    ("{Topic} study records", "restricted", ["health", "human_subjects", "personal"], ["participants"],
     "coded", None, "Collected under the study's ethics protocol.",
     "Research use under the protocol only. No attempt to identify participants."),
    ("{Topic} de-identified extract", "protected", ["human_subjects"], ["participants"],
     "deidentified", "Names, dates, and places removed; ages grouped in bands.",
     "Derived from the study records by the data core.", "Not to be linked back to the source."),
    ("{Topic} interview recordings", "restricted", ["human_subjects", "personal"], ["participants"],
     "identified", None, "Recorded with consent under the study's ethics protocol.",
     "Recordings are deleted once transcripts are checked."),
    ("Controlled-access {topic} genotypes", "restricted", ["genetic", "human_subjects", "under_agreement"],
     ["participants"], "coded", None, "Obtained from a controlled-access repository under a data use agreement.",
     "No re-identification, no redistribution, and no use outside the approved project. "
     "A model trained on it carries the same terms."),
]  # fmt: skip

# --- Agents, agreements ---------------------------------------------------------------------

AGENT_PROFILES: dict[str, dict[str, str]] = {
    "Deskhand Agent": {
        "autonomy_level": "within_limits",
        "actions": "Sets a ticket's category and priority, posts a reply, and closes password "
        "resets and access requests on its allow-list. It cannot change accounts or groups.",
        "tools": "The ticketing system (read and write, its own queue only). The knowledge base "
        "(read only).",
        "identity": "A service account, svc-deskhand, limited to the service-desk queue",
        "reversibility": "reversible",
        "human_override": "A switch in the admin console stops it at once. Any analyst can "
        "reopen a ticket it closed.",
        "memory": "Nothing between tickets beyond the ticket's own history.",
        "limits": "At most 200 actions an hour. It hands a ticket to a person after two replies.",
    },
    "Kestrel Booker": {
        "autonomy_level": "with_approval",
        "actions": "Books and moves instrument time. Drafts orders for consumables.",
        "tools": "The booking calendar (read and write). The purchasing system (drafts only).",
        "identity": "It acts as the person who asked it, with their permissions",
        "reversibility": "reversible",
        "human_override": "Every booking can be cancelled by its owner. Orders are only drafts "
        "until a person submits them.",
        "limits": "It cannot submit an order or book more than four hours at a time.",
    },
    "Saltmarsh Notebook Agent": {
        "autonomy_level": "within_limits",
        "actions": "Runs analysis steps in a lab notebook and records what it did.",
        "tools": "The electronic lab notebook (read and write). The compute cluster (submit jobs).",
        "identity": "Not yet settled: under evaluation",
        "reversibility": "mostly",
        "human_override": "Under evaluation.",
    },
    "Driftwood Reviewer": {
        "autonomy_level": "within_limits",
        "actions": "Searches the literature, downloads papers, and writes a draft review.",
        "tools": "Literature databases (read only). A scratch folder (write).",
        "reversibility": "reversible",
        "human_override": "It stops when its task window ends. Nothing it writes is used unread.",
    },
}

# (kind, title, years it runs, notice in days, renews by itself)
AGREEMENTS: list[tuple[str, str, int, int | None, bool]] = [
    ("master", "Master services agreement", 3, 90, True),
    ("data_processing", "Data processing terms", 3, 60, False),
    ("health_information", "Agreement covering health information", 2, 90, False),
    ("license", "Software license", 1, 30, True),
    ("terms_accepted", "Online terms of service", 1, None, True),
]


RETIRED_NOTES = [
    "The project this supported has ended and the tool is no longer used for it.",
    "We stopped using it when the grant finished. The data has been archived.",
    "The lab moved this work to an approved tool that is already registered.",
    "The person who ran this has left, and nobody has taken it over.",
]

CHANGED_NOTES = [
    "We now use it on a second dataset from the same study.",
    "The supplier released a new version, and we have moved to it.",
    "Two more people in the lab now use it, for the same purpose.",
    "Outputs now go into a shared report, where before they stayed in the lab.",
]

# title, the requirement, why, what is done instead
EXCEPTIONS = [
    (
        "Use before the security assessment is finished",
        "A security assessment must be complete before a tool is used with protected data.",
        "The assessment is booked but will not finish before the pilot has to start for the grant report.",
        "Only de-identified data is used until the assessment is done, and access is limited to two named people.",
    ),
    (
        "Keep prompts for ninety days instead of thirty",
        "Inputs to an AI tool are kept for no longer than thirty days.",
        "The study protocol asks for prompts to be available to the monitor for a full quarter.",
        "Prompts are kept in the lab's own encrypted storage, not with the supplier, and are deleted by a scheduled job.",
    ),
    (
        "Run the model on a workstation outside the managed fleet",
        "Models that touch protected data run on managed equipment only.",
        "The only machine with enough memory is a workstation bought on the grant, which is not yet enrolled.",
        "The workstation is off the network while the model runs, and its disk is encrypted. Enrollment is under way.",
    ),
    (
        "Share outputs with a collaborator before the agreement is signed",
        "Outputs are shared outside the institute only under a signed data use agreement.",
        "The agreement is with the collaborator's legal office and the abstract deadline falls first.",
        "Only aggregate figures are shared, with no record-level output, and the collaborator has agreed in writing to delete them on request.",
    ),
    (
        "Review a sample of outputs instead of every one",
        "A person checks every output before it is relied on.",
        "Volume has grown to several thousand items a week, more than the team can read.",
        "A random five percent is read each week, the error rate is recorded, and full review resumes if it passes two percent.",
    ),
    (
        "Use a personal account while the site license is arranged",
        "Tools are used under the institute's own agreement and accounts.",
        "Procurement has approved the license and it will be in place next month.",
        "Nothing but public material is entered, and the personal account's history is turned off.",
    ),
    (
        "Skip the annual ethics renewal while the study is paused",
        "Uses of human-subjects data keep a current ethics approval on file.",
        "Enrollment is paused and the committee has agreed to consider the renewal with the amended protocol.",
        "No new participant data is processed until the renewal is on file.",
    ),
]

EXCEPTION_NOTES = {
    "approved": [
        "Acceptable for a limited time. The measures described keep the risk about where the requirement would.",
        "Approved until the date given. Tell us if the measures stop being practical before then.",
        "Reasonable given the deadline. This will not be extended without the assessment being under way.",
    ],
    "declined": [
        "The measures do not cover the risk the requirement is there for. Use the approved alternative in the catalog.",
        "This would put restricted data outside the institute's control. We can help find another route.",
    ],
}

# days ago, what it is about ("use" or a model's name), title, description, category,
# severity, how far it got, and the actions set: (what, days allowed, done?)
INCIDENTS = [
    (
        410,
        "use",
        "A summary attributed a quote to the wrong participant",
        "A generated interview summary put one participant's words under another's name. A coordinator noticed before it was filed.",
        "wrong_output",
        "moderate",
        "closed",
        [("Re-check the summaries made that week against the recordings", 14, True)],
    ),
    (
        300,
        "use",
        "A draft with unpublished results was pasted into a consumer chat app",
        "A student pasted a results section into a personal chat account to tidy the wording. The account was not covered by the institute's agreement.",
        "unapproved_use",
        "moderate",
        "closed",
        [
            ("Remind the lab which tools are approved, at the next group meeting", 21, True),
            ("Ask the supplier to delete the conversation", 10, True),
        ],
    ),
    (
        215,
        "use",
        "Participant identifiers were sent to a supplier in prompts",
        "A batch job included study identifiers in the text sent for classification. The use was approved for de-identified text only.",
        "data_exposure",
        "high",
        "reviewed",
        [
            ("Confirm with the supplier that the prompts were deleted", 7, True),
            ("Add a check that strips identifiers before anything is sent", 30, True),
            ("Tell the ethics committee, as the protocol requires", 5, True),
        ],
    ),
    (
        140,
        "use",
        "The transcription service was down during a clinic session",
        "Recordings could not be transcribed for an afternoon. Notes were taken by hand and nothing was lost.",
        "outage",
        "low",
        "closed",
        [],
    ),
    (
        95,
        "use",
        "A citation in a grant draft did not exist",
        "A reference suggested by the writing assistant could not be found. It was caught at internal review, before submission.",
        "near_miss",
        "low",
        "closed",
        [("Add reference checking to the lab's submission checklist", 20, True)],
    ),
    (
        50,
        "use",
        "The assistant's answer disagreed with the protocol",
        "Someone thought the protocol assistant gave a wrong incubation time. On checking, the protocol had been updated and the assistant was right.",
        "",
        "",
        "dismissed",
        [],
    ),
    (
        19,
        "Brightfen Large 3",
        "The model returns different answers after a silent update",
        "Outputs for the same prompts changed last week. The supplier confirms a model update that was not announced. Several validated workflows depend on the earlier behavior.",
        "wrong_output",
        "high",
        "open",
        [
            ("Ask the supplier for the change notes and a way to pin the version", 14, False),
            ("Re-run the validation set for each use that relies on it", 30, False),
            ("Tell the owners of the uses that rely on it", 3, True),
        ],
    ),
    (
        8,
        "use",
        "Summaries were shared with a collaborator outside the agreement",
        "A set of generated summaries was emailed to a collaborator at another institution before the data use agreement was signed.",
        "data_exposure",
        "moderate",
        "contained",
        [("Ask the collaborator to delete the summaries and confirm in writing", 5, False)],
    ),
    (
        1.4,
        "use",
        "A chatbot answer was pasted into a patient-facing leaflet without review",
        "A draft leaflet went to the print queue with text nobody had checked. It was pulled before printing.",
        "",
        "",
        "reported",
        [],
    ),
]

INCIDENT_CAUSES = {
    "outage": "A fault at the supplier.",
    "unapproved_use": "The approved tool was not known to a new member of the lab.",
    "data_exposure": "The step that removes identifiers was skipped for one batch.",
    "": "The output was not checked against its source before it was used.",
}

INCIDENT_LESSONS = {
    "outage": "Keep a manual fallback for anything used in a clinic session.",
    "unapproved_use": "New starters are shown the catalog in their first week.",
    "data_exposure": "The check now runs automatically, and the job stops if it fails.",
    "": "Outputs of this kind are checked against the source before they are used.",
}
