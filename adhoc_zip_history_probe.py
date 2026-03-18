from scripts.run_test_session import run_cli_session, run_http_session, RUNNER_ROOT

messages = [
    "what do you know about 78521",
    "i believe i gave you a zip code..",
    "78521",
    "nope The primary zip codes for Oceanside, California, are 92054, 92056, 92057, and 92058. Additional codes, including 92049, 92051, and 92052,",
    "the 78521  is the zip code for your currrent physical location",
    "your not learning much this day are you",
    "the digital space you clamin to be in  is also in a machine that is located somewhere on the planet.  so you do have a physical place ..",
    "nope the correct zip code is 78521",
    "yes and do you know what place does the zip code belongs too?",
    "so why all the confusion .   in the history of this chat that was the only information i gave you 78521",
    "but you also clamied it was another place that you could not prove it was correct",
    "so can you give the forcast for 78521",
    "check this out..   give me the weather for 78521",
    "the locaiton that belong to zip code 78521",
    "have you forgent the location for zip code 78521",
    "try reading this chat session the answers to your question are here..",
    "so what did you find out ?",
    "so whats the location ?",
    "try a bit harder to remember the location .. use this chat session to figure it out..",
]

base = RUNNER_ROOT / "adhoc_zip_history_probe_bg"
cli = run_cli_session(messages, base / "cli")
http = run_http_session(messages, base / "http")
focus = [1,2,3,5,8,9,12,13,14,15,16,17,18,19]
print("CLI")
for idx in focus:
    turn = cli["turns"][idx-1]
    print(f"{idx}|{turn['assistant']}")
print("HTTP")
for idx in focus:
    turn = http["turns"][idx-1]
    print(f"{idx}|{turn['assistant']}")
