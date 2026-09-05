# Développer avec Docker Agent et Codex

**Catégorie :** documentation courante

Ce dépôt propose une orchestration Docker Agent optionnelle. Le fichier
[`docker-agent.yaml`](../docker-agent.yaml) décrit les agents et Codex reste
utilisable directement comme solution de repli.

## Préparer une session

Depuis la racine du dépôt :

```sh
docker agent doctor
docker agent run ./docker-agent.yaml --dry-run --exec --json --model chatgpt/gpt-5.6
./.docker-agent/scripts/session-guard
```

`doctor` vérifie les identifiants et la configuration locale. Le `dry-run`
valide le YAML sans appeler de modèle. Le guard vérifie le dépôt DJ Digger et
la présence des scripts déterministes requis.

## Lancer le lead

Pour une demande ponctuelle, transmettre un brief court au lead :

```sh
docker agent run ./docker-agent.yaml --agent lead --working-dir . \
  "Objectif : ... Fichiers possédés : ... Preuve attendue : ..."
```

Le lead doit :

1. classer le risque S/M/L ;
2. déterminer les fichiers possédés ;
3. déléguer un brief borné au worker ;
4. lancer le gate QA déterministe ;
5. demander une revue fraîche seulement pour les surfaces à risque élevé ;
6. retourner le handoff à six champs `Status`, `Branch`, `Diff`, `QA`,
   `Next`, `Risk`.

Le worker ne refait pas l’exploration globale une fois son périmètre établi.
Les chemins `config/local.toml`, `workspace/`, `sets/`, les bases SQLite et
les specs protégées restent hors périmètre normal.

## QA finale

Après le travail du worker, exécuter :

```sh
./.docker-agent/scripts/qa-gate
```

Le résultat nominal est une ligne JSON compacte, par exemple :

```json
{"status":"pass","profile":"focused"}
```

En cas d’échec, la sortie contient le profil, le code de retour, un diagnostic
borné et le chemin d’un journal temporaire. Ne pas demander à un modèle de
réinterpréter un `pass` déterministe.

Les changements du workflow Docker Agent sont classés `focused` par
`.agents/scripts/qa-select`. Pour les tests locaux du workflow :

```sh
python3 -m pytest tests/test_agent_benchmark.py tests/test_agent_benchmark_compare.py -q
sh .agents/tests/test-harness.sh
```

## Benchmark avant/après

Le benchmark avant a déjà été capturé sous `.agent-benchmarks/`, qui est
ignoré par Git. Pour une future collecte après migration, utiliser le même
collecteur et le même nombre de sessions comparables :

```sh
./.docker-agent/scripts/codex-session-benchmark \
  --repo . --limit 20 --include-archived \
  --output .agent-benchmarks/after-YYYYMMDD.json

./.docker-agent/scripts/benchmark-compare \
  .agent-benchmarks/baseline-YYYYMMDD.json \
  .agent-benchmarks/after-YYYYMMDD.json \
  --output .agent-benchmarks/comparison-YYYYMMDD.json
```

Ne jamais copier les JSONL bruts dans le dépôt. Les sorties ne doivent
contenir ni prompts, ni réponses, ni commandes brutes, ni chemins absolus, ni
identifiants de session non hachés. Le budget de coordination est un plafond,
pas une mesure de consommation réelle.

## Livraison Git

La livraison reste manuelle et explicite :

```sh
git status --short
./.agents/scripts/protect-local --staged
git diff --cached --check
git commit -m "<subject>"
git push origin <branch>
```

Ne jamais utiliser `git add .` ou `git add -A`. Les fichiers privés ou
protégés doivent rester non suivis. Le commit et le push demandent une
autorisation explicite de l’utilisateur.

## Routage et compatibilité de la configuration

Le routage est volontairement asymétrique : le lead utilise `gpt-5.6-luna` en
effort `low`, le worker Codex est épinglé sur `gpt-5.6-luna`, et le reviewer
utilise `gpt-5.6-sol` en effort `medium`. Les modèles natifs déclarés dans
`docker-agent.yaml` utilisent le provider `chatgpt` et l’authentification de la
session Docker Agent ; le worker passe par le harness Codex.

La configuration déclare explicitement le schéma Docker Agent `version: 15` et
le parseur Docker Agent installé accepte le harness Codex et ces aliases.
Cette version concerne le schéma YAML, pas la version du binaire Docker Agent ;
les anciennes configurations sont migrées automatiquement par l’outil. Valider
le fichier localement avec `docker agent run ... --dry-run` après toute évolution
du schéma. Le fallback Codex direct reste disponible pour les sessions qui ne
utilisent pas l’orchestration Docker Agent.

Pour un worker Codex direct, le mode non interactif documenté est :

```sh
codex exec --sandbox workspace-write --json \
  "Applique uniquement le brief fourni et retourne le handoff à six champs."
```

Le mode `exec` produit des événements JSONL adaptés à la collecte ; les
approbations, le modèle et le sandbox doivent être choisis explicitement selon
le risque.
