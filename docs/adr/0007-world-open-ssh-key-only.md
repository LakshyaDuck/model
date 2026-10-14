# SSH is key-only and world-reachable

The VM security list allows 22, 80, and 443 from `0.0.0.0/0`. Password SSH is off. 80/443 must be public so any phone can hit the public origin; 22 stays public so you can SSH from campus or mobile, not only one home IP.
