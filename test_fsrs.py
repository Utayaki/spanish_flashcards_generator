from datetime import datetime, timezone
from time import monotonic

from fsrs import Scheduler, Card, Rating, Optimizer


def utc_now() -> datetime:
    """py-fsrs expects custom datetimes to be timezone-aware UTC."""
    return datetime.now(timezone.utc)


def parse_rating(user_input: str) -> Rating:
    """
    Convert user input into a py-fsrs Rating.

    Valid inputs:
    1 / again
    2 / hard
    3 / good
    4 / easy
    """
    normalized = user_input.strip().lower()

    rating_map = {
        "1": Rating.Again,
        "again": Rating.Again,
        "a": Rating.Again,

        "2": Rating.Hard,
        "hard": Rating.Hard,
        "h": Rating.Hard,

        "3": Rating.Good,
        "good": Rating.Good,
        "g": Rating.Good,

        "4": Rating.Easy,
        "easy": Rating.Easy,
        "e": Rating.Easy,
    }

    if normalized not in rating_map:
        raise ValueError("Invalid rating. Use 1/again, 2/hard, 3/good, or 4/easy.")

    return rating_map[normalized]


def print_card_status(label: str, card: Card) -> None:
    print(f"\n--- {label} ---")
    print(f"card_id:      {card.card_id}")
    print(f"state:        {card.state}")
    print(f"step:         {card.step}")
    print(f"stability:    {card.stability}")
    print(f"difficulty:   {card.difficulty}")
    print(f"due:          {card.due}")
    print(f"last_review:  {card.last_review}")


# 1. Init scheduler
scheduler = Scheduler()

print("\nScheduler initialized:")
print(scheduler)


# 2. Create 5 cards for Spanish words.
# Your app data and FSRS scheduling object live together in RAM.
cards = [
    {
        "front": "hola",
        "back": "hello",
        "fsrs_card": Card(card_id=1),
    },
    {
        "front": "gracias",
        "back": "thank you",
        "fsrs_card": Card(card_id=2),
    },
    {
        "front": "perro",
        "back": "dog",
        "fsrs_card": Card(card_id=3),
    },
    {
        "front": "casa",
        "back": "house",
        "fsrs_card": Card(card_id=4),
    },
    {
        "front": "agua",
        "back": "water",
        "fsrs_card": Card(card_id=5),
    },
]

# Everything stays in these RAM variables.
all_review_logs = []
review_logs_by_card_id = {
    card_data["fsrs_card"].card_id: []
    for card_data in cards
}

print("\nCreated 5 Spanish cards in RAM only.")
for card_data in cards:
    print_card_status(
        label=f"Initial FSRS card for '{card_data['front']}'",
        card=card_data["fsrs_card"],
    )


# 3. Review them via user input
print("\nNow review the cards.")
print("Ratings:")
print("1 = Again  | forgot")
print("2 = Hard   | remembered with serious difficulty")
print("3 = Good   | remembered after hesitation")
print("4 = Easy   | remembered easily")

for card_data in cards:
    fsrs_card = card_data["fsrs_card"]

    print("\n========================================")
    print(f"Spanish word: {card_data['front']}")

    start = monotonic()
    input("Press Enter to show answer...")

    print(f"Answer: {card_data['back']}")

    while True:
        raw_rating = input("Your rating [1=Again, 2=Hard, 3=Good, 4=Easy]: ")

        try:
            rating = parse_rating(raw_rating)
            break
        except ValueError as error:
            print(error)

    review_duration_ms = int((monotonic() - start) * 1000)

    # This is the core FSRS call.
    # It returns a NEW updated Card object and a ReviewLog object.
    updated_card, review = scheduler.review_card(
        card=fsrs_card,
        rating=rating,
        review_datetime=utc_now(),
        review_duration=review_duration_ms,
    )

    # Keep updated card in RAM.
    card_data["fsrs_card"] = updated_card

    # Keep ReviewLog objects in RAM.
    all_review_logs.append(review)
    review_logs_by_card_id[review.card_id].append(review)

    # 5. After each rate - print(review)
    print("\nReviewLog object:")
    print(review)

    print_card_status(
        label=f"Updated FSRS card for '{card_data['front']}'",
        card=updated_card,
    )


# 6. Init Optimizer
print("\n========================================")
print("Initializing Optimizer with all ReviewLog objects in RAM...")

try:
    optimizer = Optimizer(all_review_logs)

    # Compute optimized parameters.
    # With only 5 one-time reviews, this will usually return default parameters,
    # because real FSRS optimization needs much more review history.
    optimal_parameters = optimizer.compute_optimal_parameters(verbose=True)

    print("\nOptimal parameters:")
    print(optimal_parameters)

    # Create a new scheduler with optimized parameters.
    optimal_scheduler = Scheduler(parameters=optimal_parameters)

    print("\nOptimal scheduler initialized:")
    print(optimal_scheduler)

except ImportError as error:
    print("\nOptimizer is not installed.")
    print('Install it with: pip install "fsrs[optimizer]"')
    raise error


# 7. Reschedule cards
print("\n========================================")
print("Rescheduling cards with the optimized scheduler...")

rescheduled_cards = []

for card_data in cards:
    old_card = card_data["fsrs_card"]
    logs_for_this_card = review_logs_by_card_id[old_card.card_id]

    rescheduled_card = optimal_scheduler.reschedule_card(
        card=old_card,
        review_logs=logs_for_this_card,
    )

    rescheduled_cards.append({
        "front": card_data["front"],
        "back": card_data["back"],
        "fsrs_card": rescheduled_card,
    })

    print_card_status(
        label=f"Rescheduled card for '{card_data['front']}'",
        card=rescheduled_card,
    )


print("\n========================================")
print("Done.")
print("Everything was kept in RAM only.")
print(f"Number of cards: {len(cards)}")
print(f"Number of review logs: {len(all_review_logs)}")
print(f"Number of rescheduled cards: {len(rescheduled_cards)}")
