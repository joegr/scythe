Feature: Names, places and dates in a card
  spaCy's named entity recognizer runs on every checked card. Entities are stored in the issue's
  hidden meta as spans with key "ents", style "entity", src "ner" and spaCy labels (PERSON, ORG,
  GPE, DATE, …). Debaters use them as quals: who said it, where they work, when.

  Background:
    Given a card "Quals <run>" with the text:
      """
      Alan Robock of Rutgers University warned in 2022 that a war between India and Pakistan would starve billions.
      """

  @built @slow
  Scenario: Scythe finds the people, organizations, places and dates
    Then within 5 minutes the card's issue lists these entities:
      | label  | text               |
      | PERSON | Alan Robock        |
      | ORG    | Rutgers University |
      | DATE   | 2022               |
      | GPE    | India              |
      | GPE    | Pakistan           |

  @partly @slow
  # today: the toggle is called "entities" and pointing at a name shows the raw tag, e.g. "PERSON"
  Scenario: Show the names in a card in plain words
    Given Scythe has checked the card
    When I open the card
    And I show names and places
    Then pointing at "Alan Robock" says "Person"
    And pointing at "Rutgers University" says "Organization"
    And pointing at "India" says "Place"
    And pointing at "2022" says "Date"

  @missing @slow @signed-in
  Scenario: Build quals from the names in the card
    Given I am signed in to the team's evidence
    And Scythe has checked the card
    When I open the card
    And I choose "Alan Robock" and "Rutgers University" as quals
    Then the cite reads "Robock 22, Alan Robock, Rutgers University, …"

  @missing
  Scenario: Find every card that quotes the same person
    Given two checked cards both name "Alan Robock"
    When I search for the person "Alan Robock"
    Then both cards are listed
