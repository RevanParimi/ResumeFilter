"""Authentication: sessions, email-OTP login, and the principal resolvers (S8.2).

A pure package in the house style (peer of app/portal/, app/verification/,
app/interview/): contracts and clock-injected logic first, ORM and SQL behind a
store, and every gate on the SERVICE rather than on a route.
"""
