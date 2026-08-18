// Remplace la fonction runAttack() du fichier serious-game.html
// (ou son équivalent dans ton composant React Next.js) par ceci.
// Cette version appelle ta route API au lieu d'utiliser les phrases pré-écrites.

async function runAttack(vectorId) {
  const t = selectedTarget;
  const v = VECTORS.find((v) => v.id === vectorId);

  // Petit état de chargement pendant que Claude rédige le scénario
  showLoadingState(); // à adapter : ex. afficher un spinner / message "Génération du rapport..."

  try {
    const response = await fetch("/api/attack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        targetName: t.name,
        dept: t.dept,
        risk: t.risk,
        modDone: t.modDone,
        modTotal: t.modTotal,
        vectorId: v.id,
      }),
    });

    if (!response.ok) throw new Error("Échec de la requête");

    const data = await response.json();
    // data = { success: boolean, narrative: string, module: string, agent: string }

    campaign.attempts++;
    if (data.success) campaign.success++;

    renderResult(t, v, data.success, data.narrative, data.module, data.agent);
  } catch (err) {
    console.error(err);
    showErrorState(); // à adapter : message "Impossible de générer le rapport, réessayez."
  }
}

// renderResult doit maintenant recevoir le texte et le module/agent
// directement depuis la réponse de l'API, au lieu de v.fail(t) / v.success(t) / v.module / v.agent
