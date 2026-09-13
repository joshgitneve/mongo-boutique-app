// Joué UNE SEULE FOIS, au premier démarrage, quand /data/db est vide.
// Pour le rejouer : docker compose down -v && docker compose up -d

db.createUser({
  user: "app",
  pwd: "app-password",
  roles: [{ role: "readWrite", db: "boutique" },
  { role: "dbAdmin", db: "boutique" },
  { role: "dbAdmin", db: "boutique_test" }
]
});

print("utilisateur applicatif 'app' créé sur la base boutique");
