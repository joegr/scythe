Feature: Choosing the resolution
  Every card is filed under a resolution: one of the 542 NSDA past topics (Policy, LD, PF, Big
  Questions; parsed from speechanddebate.org into nsda_topics.json with slugs like
  "ld-2024-25-novdec-adopt-wealth-tax", at most 44 characters so "topic:<slug>" fits GitHub's
  50-character label limit) or a custom resolution saved to scythe.json with a "custom-" slug.
  The chosen resolution is remembered per browser and asked for the first time a card is made.

  Background:
    Given I am signed in to the team's evidence
    And I have not chosen a resolution yet

  @built @signed-in
  Scenario: The first card asks which resolution it's for
    When I paste a clip "Soot blocks the sun." tagged "First card <run>"
    Then I see "Which topic is this card for?"
    When I search resolutions for "wealth tax"
    And I filter to "LD"
    And I choose the resolution with slug "ld-2024-25-novdec-adopt-wealth-tax"
    Then I am on the new card
    And the card's front matter has the topic slug "ld-2024-25-novdec-adopt-wealth-tax"
    And the next card I make uses that resolution without asking

  @built @signed-in
  Scenario Outline: Every NSDA event's past topics are there
    When I open the resolution picker
    And I filter to "<event>"
    Then the list includes "<resolution>"

    Examples:
      | event  | resolution                                                       |
      | policy | Resolved: The United States federal government should significantly increase its exploration and/or development of the Arctic. |
      | LD     | Resolved: De-extinction is unethical.                            |
      | PF     | Resolved: The United States federal government should substantially increase its military presence in the Arctic. |

  @built @signed-in
  Scenario: Write a resolution that isn't on the list
    When I open the resolution picker
    And I write my own resolution "Schools should ban phones <run>"
    Then scythe.json lists a topic with resolution "Resolved: Schools should ban phones <run>" and a slug starting "custom-schools-ban-phones"

  @partly @signed-in
  # today: closing the picker during a cut leaves the reader's Cut button disabled until reload
  Scenario: Closing the picker doesn't lose the cut
    Given a pasted source "Picker study <run>" by "Alan Robock" in "Nature Food" on "2022-08-15" with text "Soot blocks the sun."
    When I open that source in the reader
    And I select "Soot blocks the sun." in the source
    And I write the tag "Picker <run>"
    And I cut the card
    And I close the resolution picker without choosing
    Then the cut button is enabled
    And my selection and tag are still there

  @partly @signed-in
  # today: the list silently stops at 80 topics
  Scenario: The whole list is reachable
    When I open the resolution picker
    And I filter to "LD"
    Then I can scroll through all 235 LD resolutions

  @partly
  # today: custom resolutions show their slug, e.g. "custom-schools-ban-phones-k3x9z", in Library and Search
  Scenario: A custom resolution reads as the resolution everywhere
    Given a card filed under a custom resolution "Resolved: Schools should ban phones."
    When I look at the library
    Then I see "Resolved: Schools should ban phones."
