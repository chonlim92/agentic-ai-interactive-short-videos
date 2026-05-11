/**
 * Initialize the JSON data store.
 * Run with: node scripts/init-db.js
 */
const path = require("path");
const fs = require("fs");

const dataDir = path.join(__dirname, "..", "data");
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const storePath = path.join(dataDir, "store.json");

if (fs.existsSync(storePath)) {
  console.log(`Store already exists at ${storePath}`);
} else {
  const empty = {
    episodes: [],
    vote_options: [],
    votes: [],
    next_id: { episodes: 1, vote_options: 1, votes: 1 },
  };
  fs.writeFileSync(storePath, JSON.stringify(empty, null, 2));
  console.log(`Store initialized at ${storePath}`);
}
