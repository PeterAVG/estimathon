import math
import os
from typing import Any, Dict
import numpy as np
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import streamlit as st
from dataclasses import dataclass, field
import pandas as pd
from questions import QUESTIONS

# read SLACK_TOKEN from .env file
from dotenv import load_dotenv

from teams import TEAMS

# change CHANNEL_ID to the channel you want to read
CHANNEL_ID = "C06B3US0JH5"  # nytår2023test
# number of questions in Estimation Game
NUM_QUESTIONS = len(QUESTIONS)
# NUMBER OF TEAMS
NUM_TEAMS = len(TEAMS)
# NUMBER OF ANSWERS PER TEAM
NUM_ANSWERS = 18

load_dotenv()

# Initialize a Web client
client = WebClient(token=os.environ["SLACK_TOKEN"])

if "state" not in st.session_state:
    print("\n\nInitializing session state...")
    st.session_state.state: Dict[str, Any] = {}  # type: ignore

STATE = st.session_state.state


def join_channel(channel_id) -> Any:
    url = "https://slack.com/api/conversations.join"

    headers = {"Authorization": f"Bearer {os.environ['SLACK_TOKEN']}"}

    payload = {"channel": channel_id}

    response = requests.post(url, headers=headers, data=payload)
    print(response.text)


join_channel(CHANNEL_ID)


@dataclass
class Answer:
    question_number: int
    interval1: int
    interval2: int

    def score(self) -> float:
        truth = int(QUESTIONS[f"Q{self.question_number}"]["svar"])
        if self.interval1 <= truth <= self.interval2:
            return math.floor(self.interval2 / self.interval1)
        else:
            return np.infty


@dataclass
class Team:
    team_name: str
    answers: Dict[str, Answer] = field(default_factory=dict)
    count: int = field(init=False)

    def __post_init__(self):
        self.count = 0

    def score(self):
        q_dict = {}
        inner_sum = 0
        no_good = 0
        for a in self.answers.values():
            q_dict[a.question_number] = a.score()
            inner_sum += a.score() if not a.score() == np.infty else 0
            no_good += 1 if not a.score() == np.infty else 0

        return (10 + inner_sum) * 2 ** (NUM_QUESTIONS - no_good)

    def as_list_of_dicts(self):
        return [
            {
                "Team name": self.team_name,
                "Question": f"Q{answer.question_number}",
                "Score": answer.score(),
            }
            for answer in self.answers.values()
        ]


def get_slack_history(channel_id) -> Any:
    try:
        # Call the conversations.history method using the built-in WebClient
        result = client.conversations_history(channel=channel_id)

        # Print message text
        for message in result["messages"]:
            print(message["text"])

    except SlackApiError as e:
        print(f"Error: {e.response['error']}")
        raise e

    return result


def send_slack_message(channel_id, message) -> None:
    # Slack API endpoint for sending messages
    url = "https://slack.com/api/chat.postMessage"

    # Headers for the request
    headers = {
        "Authorization": f'Bearer {os.environ["SLACK_TOKEN"]}',
        "Content-Type": "application/json",
    }

    # Data payload for the request
    data = {"channel": channel_id, "text": message}

    # Send a POST request to the Slack API
    response = requests.post(url, headers=headers, json=data)

    # assert response.status_code == 200, response.text
    if response.status_code != 200:
        print(response.text)
        raise Exception(response.text)


def send_slack_message_v2(channel_id, message) -> None:
    # use client to send message
    try:
        # Call the conversations.history method using the built-in WebClient
        result = client.chat_postMessage(channel=channel_id, text=message)

    except SlackApiError as e:
        print(f"Error: {e.response['error']}")
        raise e

    return result


# function to get conversations history and parse it into a dictionary
def get_res() -> Dict[str, Team]:
    # get slack message history
    messages = get_slack_history(CHANNEL_ID)
    _messages = messages["messages"]
    # sort messages by timestamp
    _messages.sort(key=lambda x: x["ts"])

    res: Dict[str, Team] = {}

    for message in _messages:
        split = message["text"].split("\n")
        if len(split) != 4:
            print(f"Invalid message: {message['text']}")
            continue

        team_name = split[0]
        question_number = int(split[1])
        answer_interval1 = int(split[2])
        answer_interval2 = int(split[3])

        if question_number > NUM_QUESTIONS:
            print(
                f"Invalid question number: {question_number} for message: {message['text']}"
            )
            continue

        if answer_interval1 > answer_interval2:
            print(
                f"Invalid answer interval: {answer_interval1} > {answer_interval2} for message: {message['text']}"
            )
            continue

        if answer_interval1 <= 0:
            print(
                f"Invalid answer interval: {answer_interval1} <= 0 for message: {message['text']}"
            )
            continue

        answer = Answer(question_number, answer_interval1, answer_interval2)

        if team_name not in res:
            team = Team(team_name, {question_number: answer})
            team.count += 1
            res[team_name] = team
        else:
            # now assert that a maximum of NUM_ANSWERS answers have been submitted for this team
            if res[team_name].count >= NUM_ANSWERS:
                print(
                    f"{team_name} have alread answered {NUM_ANSWERS} times... No more answers allowed"
                )
                continue

            # otherwise, add answer to team and increment count
            res[team_name].answers[question_number] = answer
            res[team_name].count += 1

    return res


# Function to render the input page
def input_page():
    st.title("Input Page")

    # team name is dropdown from TEAMS
    team_name = st.selectbox("Team Name", TEAMS)
    # display answers for this team if present in STATE
    res = get_res()
    _count = res[team_name].count if team_name in res else 0
    st.write(f"{team_name} has submitted {_count}/{NUM_ANSWERS} answers")

    question_number_str = st.selectbox(
        "Question Number",
        [
            f"Q{i}: " + QUESTIONS[f"Q{i}"]["Spørgsmål"]
            for i in range(1, NUM_QUESTIONS + 1)
        ],
    )
    question_number = int(question_number_str.split(":")[0][1:])  # type: ignore
    answer_interval1 = st.number_input("Answer Interval 1", min_value=1, step=1)
    answer_interval2 = st.number_input("Answer Interval 2", min_value=1, step=1)

    if _count >= NUM_ANSWERS:
        st.error(
            f"{team_name} have alread answered {NUM_ANSWERS} times... No more answers allowed"
        )
        return

    if question_number > NUM_QUESTIONS:
        st.error(f"Invalid question number: {question_number} for input")
        return

    if answer_interval1 > answer_interval2:
        st.error(
            f"Invalid answer interval: {answer_interval1} > {answer_interval2} for input"
        )
        return

    if answer_interval1 <= 0:
        st.error(f"Invalid answer interval: {answer_interval1} <= 0 for input")
        return

    if answer_interval2 <= 0:
        st.error(f"Invalid answer interval: {answer_interval2} <= 0 for input")
        return

    if st.button("Submit"):
        # send message to slack channel
        message = (
            f"{team_name}\n{question_number}\n{answer_interval1}\n{answer_interval2}"
        )
        assert len(message.split("\n")) == 4
        send_slack_message_v2(CHANNEL_ID, message)

        st.success(
            f"Submitted: Team {team_name}, Question {question_number}, Answer Interval 1 {answer_interval1}, Answer Interval 2 {answer_interval2}"
        )


# Function to render the results page
def results_page():
    st.title("Results Page")

    # get slack history
    res = get_res()

    # save state to be used elsewhere
    # STATE["res"] = res

    # convert to dataframe
    entries = []
    for team in res.values():
        entries.extend(team.as_list_of_dicts())

    df = pd.DataFrame(entries)
    # shape dataframe such that column "Team name" is columns, "Question" is index, "Score" is values
    df = df.pivot(index="Question", columns="Team name", values="Score")
    for team_name in df.columns:
        df.loc["Score", team_name] = res[team_name].score()

    # Add question index if it is missing
    for i in range(1, NUM_QUESTIONS + 1):
        if f"Q{i}" not in df.index:
            df.loc[f"Q{i}", :] = np.infty

    # sort dataframe according to question index
    df = df.sort_index()
    # manually specify index order
    df = df.reindex(index=[f"Q{i}" for i in range(1, NUM_QUESTIONS + 1)] + ["Score"])

    # Display results here as a table with:
    # columns: Team Name 1.. Team Name N
    # rows: Question 1.. Question N
    # cells: score per team per question
    # df = df.replace(np.nan, np.infty).applymap(lambda x: np.infty if x == np.infty else int(x))
    df = df.replace(np.infty, np.nan)
    # df = df.applymap(lambda x: "" if pd.isna(x) else int(x))
    styled_df = df.style.background_gradient(cmap="RdYlGn_r", axis=None).format(
        "{:.0f}"
    )
    st.table(styled_df)


def main() -> None:
    if "initialized" not in STATE:
        STATE["initialized"] = True
    else:
        assert STATE["initialized"]

    # Sidebar navigation
    page = st.sidebar.selectbox(
        "Choose a page", ["Input Page", "Results Page", "Questions"]
    )

    if page == "Input Page":
        input_page()
    elif page == "Results Page":
        results_page()
    elif page == "Questions":
        st.title("Questions")
        for i in range(1, NUM_QUESTIONS + 1):
            st.write(f"Q{i}: " + QUESTIONS[f"Q{i}"]["Spørgsmål"])
            # st.markdown(
            #     f"Answer: {QUESTIONS[f'Q{i}']['svar']} ([source]({QUESTIONS[f'Q{i}']['kilde']}))"
            # )


if __name__ == "__main__":
    main()
