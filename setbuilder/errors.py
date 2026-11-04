class AnalysisUnavailableError(RuntimeError):
    """Un modèle d'analyse n'est pas utilisable (extra absent, poids introuvables, hors-ligne).

    Interrompt le batch : inutile de continuer, tous les tracks échoueraient pareil.
    """
