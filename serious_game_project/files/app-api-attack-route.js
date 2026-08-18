// Fichier à placer dans ton projet Next.js à :
//   app/api/attack/route.js   (App Router — Next.js 13+)
//
// Variable d'environnement à ajouter sur Vercel (Project Settings > Environment Variables) :
//   ANTHROPIC_API_KEY = sk-ant-xxxxxxxx
// (jamais exposée au client — cette route tourne uniquement côté serveur)

// Poids d'efficacité par vecteur — reste ici, côté serveur, pour ne pas être trafiqué
const VECTOR_WEIGHTS = {
  email: 1.0,
  vishing: 1.1,
  usb: 0.9,
  qr: 1.05,
  osint: 0.85,
};

const VECTOR_LABELS = {
  email: "un email de phishing ciblé",
  vishing: "un appel de vishing",
  usb: "une clé USB piégée déposée dans un lieu de passage",
  qr: "un QR code piégé (quishing)",
  osint: "un faux profil professionnel sur les réseaux sociaux (OSINT)",
};

const VECTOR_MODULES = {
  email: { module: "Reconnaître le phishing", agent: "PhishHunter" },
  vishing: { module: "Se méfier des appels non sollicités", agent: "VoiceGuard" },
  usb: { module: "Dangers des supports amovibles", agent: "EndpointWatch" },
  qr: { module: "Repérer les QR codes frauduleux", agent: "QRSentinel" },
  osint: { module: "Protéger son empreinte numérique", agent: "OSINTRadar" },
};

export async function POST(request) {
  try {
    const body = await request.json();
    const { targetName, dept, risk, modDone, modTotal, vectorId } = body;

    // Validation basique des entrées
    if (
      typeof targetName !== "string" ||
      typeof risk !== "number" ||
      !VECTOR_WEIGHTS[vectorId]
    ) {
      return Response.json({ error: "Paramètres invalides" }, { status: 400 });
    }

    // 1. Calcul du résultat côté serveur (pas trafiquable par le client)
    const weight = VECTOR_WEIGHTS[vectorId];
    const pSuccess = Math.min(0.95, Math.max(0.03, (risk / 100) * weight));
    const success = Math.random() < pSuccess;

    // 2. Génération du scénario par Claude
    const vectorLabel = VECTOR_LABELS[vectorId];
    const prompt = `Tu rédiges une seule phrase, en français, pour un serious game de sensibilisation à la cybersécurité dans une banque fictive.

Contexte :
- Cible : ${targetName}, département ${dept}
- Score de risque : ${risk}/100
- Modules de formation complétés : ${modDone}/${modTotal}
- Vecteur d'attaque utilisé : ${vectorLabel}
- Résultat de la tentative : ${success ? "ÉCHEC DE LA CIBLE (elle se fait piéger)" : "SUCCÈS DE LA CIBLE (elle détecte et déjoue l'attaque)"}

Consignes :
- Écris UNE seule phrase (pas d'intro, pas de guillemets, pas de nom en début de phrase — elle commencera par un verbe, ex: "clique sur..." ou "reconnaît...").
- Reste factuel et pédagogique, jamais moqueur envers la personne.
- Adapte le niveau de détail au score de risque et au taux de complétion des modules (une personne bien formée agit avec méthode ; une personne peu formée agit par réflexe ou impatience).
- Ne mentionne pas le score ni les modules explicitement dans la phrase.

Réponds uniquement avec la phrase, rien d'autre.`;

    const claudeResponse = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 200,
        messages: [{ role: "user", content: prompt }],
      }),
    });

    if (!claudeResponse.ok) {
      const errText = await claudeResponse.text();
      console.error("Erreur API Anthropic:", errText);
      return Response.json({ error: "Échec de génération du scénario" }, { status: 502 });
    }

    const claudeData = await claudeResponse.json();
    const narrative = claudeData.content
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join(" ")
      .trim();

    const { module, agent } = VECTOR_MODULES[vectorId];

    // 3. Réponse renvoyée au client
    return Response.json({
      success,
      narrative,
      module,
      agent,
    });
  } catch (err) {
    console.error("Erreur route /api/attack:", err);
    return Response.json({ error: "Erreur serveur" }, { status: 500 });
  }
}
