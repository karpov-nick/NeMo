import argparse
import json
import random

from assistant_utils import process_assistant
from tqdm import tqdm


"""
Example format:
    
    {"taskname": "intent_and_slot", "utterance": "who was john dillinger", "label": "\nIntent: qa_factoid\nSlots: person(john dillinger)"}
    {"taskname": "intent_and_slot", "utterance": "can you play my favorite music", "label": "\nIntent: play_music\nSlots: None"}
    {"taskname": "intent_and_slot", "utterance": "is adele going to go on tour", "label": "\nIntent: qa_factoid\nSlots: artist_name(adele)"}
    {"taskname": "intent_and_slot", "utterance": "will the temperature be in the today", "label": "\nIntent: weather_query\nSlots: weather_descriptor(temperature), date(today)"}

"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=str, default="data/assistant/NLU-Evaluation-Data-master")
    parser.add_argument("--nemo-format-dir", type=str, default="data/assistant/nemo-format")
    parser.add_argument("--output-dir", type=str, default="data/assistant")
    parser.add_argument("--save-name-base", type=str, default="assistant")
    parser.add_argument("--make-ground-truth", action='store_true')
    parser.add_argument("--include-options", action='store_true')
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.random_seed)
    process_assistant(args.source_dir, args.nemo_format_dir, modes=["train", "test"])

    intent_dict = open(f"{args.nemo_format_dir}/dict.intents.csv").readlines()
    slot_dict = open(f"{args.nemo_format_dir}/dict.slots.csv").readlines()

    # Convert train set to prompt learning format
    train_utterance_lines = open(f"{args.nemo_format_dir}/train.tsv").readlines()[1:]
    train_slot_lines = open(f"{args.nemo_format_dir}/train_slots.tsv").readlines()
    train_examples = list(zip(train_utterance_lines, train_slot_lines))

    random.shuffle(train_examples)
    train_utterance_lines, train_slot_lines = zip(*train_examples)
    train_save_path = f"{args.output_dir}/{args.save_name_base}_train.jsonl"

    process_data_for_prompt_learning(
        train_utterance_lines, train_slot_lines, intent_dict, slot_dict, train_save_path, args.include_options,
    )

    # Split test set into validation and test sets
    test_utterance_lines = open(f"{args.nemo_format_dir}/test.tsv").readlines()[1:]
    test_slot_lines = open(f"{args.nemo_format_dir}/test_slots.tsv").readlines()
    val_half = len(test_utterance_lines) // 2

    test_examples = list(zip(test_utterance_lines, test_slot_lines))
    random.shuffle(test_examples)
    test_utterance_lines, test_slot_lines = zip(*test_examples)

    # Convert val set to prompt learning format
    val_utterance_lines = test_utterance_lines[:val_half]
    val_slot_lines = test_slot_lines[:val_half]
    val_save_path = f"{args.output_dir}/{args.save_name_base}_val.jsonl"

    process_data_for_prompt_learning(
        val_utterance_lines, val_slot_lines, intent_dict, slot_dict, val_save_path, args.include_options,
    )

    # Convert test set to prompt learning format
    test_utterance_lines = test_utterance_lines[val_half:]
    test_slot_lines = test_slot_lines[val_half:]
    test_save_path = f"{args.output_dir}/{args.save_name_base}_test.jsonl"

    process_data_for_prompt_learning(
        test_utterance_lines,
        test_slot_lines,
        intent_dict,
        slot_dict,
        test_save_path,
        args.include_options,
        make_ground_truth=args.make_ground_truth,
    )


def process_data_for_prompt_learning(
    utterance_lines, slot_lines, intent_dict, slot_dict, save_path, include_options, make_ground_truth=False
):
    """
    Formats each line in the utterance file as a json object 
    with intent and slot labels.

    """
    save_file = open(save_path, "w")
    print(f"Saving data to {save_path}")

    # List all possible intent and slot lables
    if include_options:
        all_intents = ", ".join([intent.strip() for intent in intent_dict])
        all_slots = ", ".join([slot.strip() for slot in slot_dict])
        # all_labels = f"possible intents: {all_intents}\n\npossible slots: {all_slots}\n\n"

    for line_idx, line in enumerate(tqdm(utterance_lines)):
        # Get utterance and intent label
        utterance, intent_label_idx = line.split("\t")
        intent_label_idx = int(intent_label_idx.strip())
        intent_label = intent_dict[intent_label_idx].strip()
        slot_line = slot_lines[line_idx].strip().split()

        # Get and foramt all slot labels for the utterance
        slot_labels = get_slots(slot_line, utterance, slot_dict)

        if include_options:
            example_json = {
                "taskname": "intent_and_slot",
                "intent options": all_intents,
                "slot_options": all_slots,
                "utterance": utterance,
            }
        else:
            example_json = {
                "taskname": "intent_and_slot",
                "utterance": utterance,
            }

        # Dont want test examples to have labels
        if "_test" not in save_path or make_ground_truth:
            example_json["label"] = f"\nIntent: {intent_label}\nSlots: {slot_labels}"

        save_file.write(json.dumps(example_json) + "\n")


def get_slots(slot_line, utterance, slot_dict):
    """
    Formats slot labels for an utterance. Ensures the multiword 
    slot labels are grouped together. For example the words
    'birthday party' should be grouped together under the 
    same event_name label like event_name(birthday party)
    instead of event_name(birthday), event_name(party).

    """
    # Get slots and their labels
    utterance_words = utterance.split()
    slots_and_labels = []
    prev_slot_label = 'O'
    prev_word_idx = 0
    current_word = ""

    if len(utterance_words) != len(slot_line):
        slot_line = slot_line[1:]

    for word_idx, slot_label_idx in enumerate(slot_line):
        word = utterance_words[word_idx]
        slot_label = slot_dict[int(slot_label_idx)].strip()

        # Only care about words with labels
        if slot_label != 'O':

            # Keep multiword answers together
            if prev_slot_label == slot_label and prev_word_idx == word_idx - 1:
                current_word += " " + word

            # Previous answer has ended and a new one is starting
            else:
                if current_word != "":
                    slots_and_labels.append(f"{prev_slot_label}({current_word})")
                current_word = word

            prev_word_idx = word_idx
            prev_slot_label = slot_label.strip()

    # Add last labeled word to list of slots and labels if the utterance is over
    if current_word != "" and prev_slot_label != 'O':
        slots_and_labels.append(f"{prev_slot_label}({current_word})")

    # Format slot labels
    if not slots_and_labels:
        slot_labels = "None"
    else:
        slot_labels = ", ".join(slots_and_labels)

    return slot_labels


if __name__ == "__main__":
    main()
