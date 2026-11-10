# Project working agreement

- This directory is the only local Git checkout for this project. Do not create additional clones or Git worktrees.
- Before each code change, create and switch to a fresh feature/fix branch from main. Never edit application code directly on main.
- Finish implementation and relevant checks on the branch, commit, then merge the finished branch into main. main represents the final working system.
- Synchronize the feature branch and merged main to the configured GitHub origin when authorized by the user, as it is in this conversation.
- Keep secrets, .env, datasets, SQLite databases, model weights, dependency folders and logs out of Git. .env.example contains placeholders only.
- Keep the local system rooted here; real source data lives in ../公开数据 and is read-only.
- Keep design documents and the three diagrams aligned with meaningful architecture changes.
