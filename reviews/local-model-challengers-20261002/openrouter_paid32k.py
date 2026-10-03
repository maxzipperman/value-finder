"""Only author-approved progress cases; shared lock and combined $1 phase caps."""
from openrouter_paid import main

if __name__ == "__main__":
    main("openrouter-paid32k-requests.json", "441f14b4b605d49e1b9fcc0cc6ee123dd32e7e22ceeff41b213a27c8e34f0156", "openrouter-paid32k", 32768, True)
