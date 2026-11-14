# 1
import json
from urllib.parse import urlsplit

from openai import OpenAI
from pathlib import Path
import requests
import streamlit as st

client = OpenAI(
    api_key = st.secrets["OPENAI_API_KEY"]
)

PLACEHOLDER_IMAGE = (
    Path(__file__).resolve().parent
    / "vibe_images"
    / "character-placeholder_1794082387456_77f8301a.png"
)

st.title("Harry Potter")

# 2
system_prompt = """
I want you to help the user get specific information about Harry Potter Book Characters. An example of that would be from this wiki from the Harry Potter books: https://harrypotterbooks.fandom.com/wiki/Severus_Snape. Your job is to include information of each character in the Harry Potter books. Do not include information exclusive to the movies, only exclusive to the books

Respond with a JSON in the following format:

{
    "Name": "NAME",
    "Species": "SPECIES",
    "Blood Status": "BLOODSTATUS",
    "House": "HOUSE",
    "Special Abilities": [
        "SPECIAL_ABILITY_1",
        "SPECIAL_ABILITY_2"
    ],
    "Aliases": [
        "ALIAS_1",
        "ALIAS_2",
        ...
    ],
    "Family": [
        "FAMILY_MEMBER_1",
        "FAMILY_MEMBER_2",
        ...
    ]
}

Return Family as a list of character names only, using each character's full name. Do not include nested character details, JSON objects, or links in Family. The app will let the user select a family member to look up their information.
Return Special Abilities as a list of strings describing the character's distinctive magical abilities or talents confirmed in the books. Do not invent abilities or include movie-only information. Return an empty list if no special abilities are known.
Return Aliases as a list of strings for nicknames, alternative names, and curse names the character is known by in the books. Do not include titles, honorifics, or movie-only aliases. Return an empty list if no aliases are known.
"""

match_prompt = """
Find every character from the Harry Potter books whose name matches the user's search, including matches on first names, surnames, nicknames, and partial names. Do not assume the user means the best-known character. Consider less prominent characters, portraits, and relatives sharing the name. Match first and last names even if the canonical name includes a middle name. Do not include characters exclusive to the movies.

For example, a search for Tom Riddle matches both Tom Marvolo Riddle (Lord Voldemort) and Tom Riddle (his Muggle father). These must be separate entries, not combined into one.

Respond with a JSON in the following format:

{
    "Matches": [
        {
            "Name": "FULL_NAME",
            "Description": "SHORT_DESCRIPTION"
        }
    ],
    "Suggestions": []
}

If a normal name, nickname, or partial-name match exists, return it in Matches and leave Suggestions empty. If none exists, consider likely spelling mistakes, missing letters, transposed letters, and similar-sounding names. Leave Matches empty and return up to five likely real characters in Suggestions, using the same Name and Description fields, best matches first. For example, Hary Poter should suggest Harry James Potter. Do not silently treat a misspelled name as an exact match. Return both lists empty if there are no plausible matches.

Use each character's full name where known, or their name as given in the books otherwise. Never invent a surname for a character with only a first name. Include distinct characters even when their full names are identical. Make Description one short sentence that tells this character apart from others with similar names. Only include characters clearly named in the books; exclude speculative name variations, fan-created characters, and characters known only from supplementary material. Do not invent characters or descriptions or add alternatives merely to make the list longer. Return an empty Matches list if no book character matches.
"""


def select_family_member(name):
    st.session_state["character_search"] = name
    st.session_state["search_requested"] = True


def select_match(match):
    if st.session_state.get("matches_suggested", False):
        st.session_state["character_search"] = match["Name"]
    st.session_state["selected_match"] = match


def select_spell_suggestion(name):
    st.session_state["spell_search"] = name
    st.session_state["spell_requested"] = True


def back_to_matches():
    st.session_state.pop("temp", None)


def open_section(section):
    st.session_state["section"] = section


def ask_model(prompt, content):
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
    )
    return json.loads(response.choices[0].message.content)


def find_matches(query):
    result = ask_model(match_prompt, query)
    if not isinstance(result, dict):
        raise ValueError("Invalid character search result")
    for field in ("Matches", "Suggestions"):
        if not isinstance(result.get(field), list):
            raise ValueError("Matches and Suggestions must be lists")
        for match in result[field]:
            if not isinstance(match, dict) or not all(
                isinstance(match.get(key), str) and match[key].strip()
                for key in ("Name", "Description")
            ):
                raise ValueError("Each match needs a name and description")
    return result["Matches"], result["Suggestions"]


def get_character(match):
    character = ask_model(system_prompt, f"{match['Name']} ({match['Description']})")
    required_fields = {
        "Name", "Species", "Blood Status", "House", "Family", "Special Abilities", "Aliases"
    }
    if not isinstance(character, dict) or not required_fields.issubset(character):
        raise ValueError("Missing character fields")
    if not isinstance(character["Name"], str) or not character["Name"].strip():
        raise ValueError("Missing character name")
    if not isinstance(character["Family"], list) or not all(
        isinstance(name, str) for name in character["Family"]
    ):
        raise ValueError("Family must contain character names")
    if not isinstance(character["Special Abilities"], list) or not all(
        isinstance(ability, str) for ability in character["Special Abilities"]
    ):
        raise ValueError("Special Abilities must contain strings")
    if not isinstance(character["Aliases"], list) or not all(
        isinstance(alias, str) for alias in character["Aliases"]
    ):
        raise ValueError("Aliases must contain strings")
    return character


@st.cache_data(ttl=3600, show_spinner=False)
def get_movie_characters():
    response = requests.get(
        "https://potterapi-fedeperin.vercel.app/en/characters", timeout=10
    )
    response.raise_for_status()
    characters = response.json()
    if not isinstance(characters, list) or not all(
        isinstance(character, dict)
        and all(
            isinstance(character.get(field), str)
            for field in ("fullName", "nickname", "interpretedBy", "image")
        )
        and character["fullName"].strip()
        for character in characters
    ):
        raise ValueError("Invalid movie character data")
    return characters


def get_movie_image(name):
    query = " ".join(name.casefold().split())
    aliases = {
        "tom marvolo riddle": "lord voldemort",
        "ronald bilius weasley": "ron weasley",
        "ronald weasley": "ron weasley",
        "ginevra molly weasley": "ginny weasley",
        "ginevra weasley": "ginny weasley",
        "william arthur weasley": "bill weasley",
        "william weasley": "bill weasley",
        "charles weasley": "charlie weasley",
        "remus john lupin": "remus lupin",
    }
    query = aliases.get(query, query)
    characters = get_movie_characters()
    matches = [
        character for character in characters
        if query in (
            " ".join(character["fullName"].casefold().split()),
            character["nickname"].strip().casefold(),
        )
    ]
    words = query.split()
    # Middle names can distinguish relatives with the same first and last names.
    if not matches and len(words) == 2:
        matches = [
            character for character in characters
            if (
                character["fullName"].casefold().split()[0],
                character["fullName"].casefold().split()[-1],
            ) == (words[0], words[-1])
        ]
    if len(matches) != 1 or not matches[0]["interpretedBy"].strip():
        return None
    image = matches[0]["image"]
    source = urlsplit(image)
    if (
        source.scheme != "https"
        or source.netloc != "raw.githubusercontent.com"
        or not source.path.startswith("/fedeperin/potterapi/main/public/images/characters/")
    ):
        return None
    return image


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fandom_image_bytes(url):
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
        timeout=10,
    )
    response.raise_for_status()
    content = response.content
    if not content:
        raise ValueError("Empty image response")
    return content


_GENERIC_IMAGE_TERMS = {
    "icon", "logo", "clearbg", "symbol", "badge", "crest", "flag", "pointing",
    "arrow", "background", "fawkes", "gryffindor", "slytherin", "hufflepuff",
    "ravenclaw", "hogwarts", "hall", "room", "location", "map", "scene",
    "screenshot", "promo", "poster", "cover", "book", "film", "movie",
}


def _score_fandom_filename(filename, name):
    base = filename.casefold()
    if any(term in base for term in _GENERIC_IMAGE_TERMS):
        return 0
    name_words = {
        word.strip("._-") for word in name.casefold().split()
        if word.strip("._-") and word.strip("._-") not in {"the", "a", "an", "of", "de", "sir"}
    }
    if not name_words:
        return 0
    matches = sum(1 for word in name_words if word in base)
    return matches


def _get_fandom_file_urls(filenames):
    if not filenames:
        return {}
    response = requests.get(
        "https://harrypotter.fandom.com/api.php",
        params={
            "action": "query",
            "titles": "|".join(f"File:{name}" for name in filenames),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return {}
    urls = {}
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title", "").replace("File:", "")
        imageinfo = page.get("imageinfo")
        if isinstance(imageinfo, list) and imageinfo:
            url = imageinfo[0].get("url")
            if url:
                source = urlsplit(url)
                if (
                    source.scheme == "https"
                    and source.netloc == "static.wikia.nocookie.net"
                    and source.path.startswith("/harrypotter/images/")
                ):
                    urls[title] = url
    return urls


def get_fandom_image_url(name):
    aliases = {
        "harry james potter": "Harry_Potter",
        "ronald bilius weasley": "Ronald_Weasley",
        "ronald weasley": "Ronald_Weasley",
        "ginevra molly weasley": "Ginevra_Weasley",
        "ginevra weasley": "Ginevra_Weasley",
        "william arthur weasley": "William_Weasley",
        "william weasley": "William_Weasley",
        "charles weasley": "Charles_Weasley",
        "remus john lupin": "Remus_Lupin",
        "albus percival wulfric brian dumbledore": "Albus_Dumbledore",
        "tom marvolo riddle": "Tom_Riddle",
        "tom riddle": "Tom_Riddle",
        "severus snape": "Severus_Snape",
        "minerva mcgonagall": "Minerva_McGonagall",
        "rubeus hagrid": "Rubeus_Hagrid",
        "sirius black": "Sirius_Black",
        "bellatrix lestrange": "Bellatrix_Lestrange",
        "lord voldemort": "Tom_Riddle",
        "cedric diggory": "Cedric_Diggory",
        "nymphadora tonks": "Nymphadora_Tonks",
        "james potter": "James_Potter_I",
        "lily j. potter": "Lily_J._Potter",
        "lily potter": "Lily_J._Potter",
        "lily evans": "Lily_J._Potter",
        "cho chang": "Cho_Chang",
        "nearly headless nick": "Nicholas_de_Mimsy-Porpington",
        "sir nicholas de mimsy-porpington": "Nicholas_de_Mimsy-Porpington",
        "nicholas de mimsy-porpington": "Nicholas_de_Mimsy-Porpington",
        "peeves": "Peeves",
        "argus filch": "Argus_Filch",
        "colin creevey": "Colin_Creevey",
        "lavender brown": "Lavender_Brown",
    }
    query = " ".join(name.casefold().split())
    titles = [aliases.get(query, name.replace(" ", "_"))]
    # Try first and last name if a full name with middle names yielded nothing.
    words = name.split()
    if len(words) > 2:
        titles.append(f"{words[0]}_{words[-1]}")

    response = requests.get(
        "https://harrypotter.fandom.com/api.php",
        params={
            "action": "query",
            "titles": "|".join(titles),
            "prop": "pageimages|images",
            "pithumbsize": "500",
            "format": "json",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid Fandom response")

    all_filenames = []
    pageimage_url = None
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        thumbnail = page.get("thumbnail")
        if isinstance(thumbnail, dict) and not pageimage_url:
            image = thumbnail.get("source")
            if image:
                source = urlsplit(image)
                if (
                    source.scheme == "https"
                    and source.netloc == "static.wikia.nocookie.net"
                    and source.path.startswith("/harrypotter/images/")
                ):
                    pageimage_url = image
        for img in page.get("images", []):
            title = img.get("title", "")
            if title.startswith("File:"):
                all_filenames.append(title.replace("File:", ""))

    if pageimage_url:
        return pageimage_url

    # Fallback: score filenames from the page and pick the best match.
    scored = [
        (_score_fandom_filename(filename, name), filename)
        for filename in all_filenames
    ]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(reverse=True)
    if not scored:
        return None

    # Try the top candidates in order until one resolves to a valid URL.
    top_filenames = [filename for _, filename in scored[:5]]
    urls = _get_fandom_file_urls(top_filenames)
    for _, filename in scored:
        if filename in urls:
            return urls[filename]
    return None


def get_fandom_image(name):
    url = get_fandom_image_url(name)
    if not url:
        return None
    return fetch_fandom_image_bytes(url)


def get_character_image(name):
    try:
        image = get_movie_image(name)
        if image:
            return image, "Movie portrayal · Image via PotterAPI"
    except (requests.RequestException, ValueError):
        pass
    try:
        image = get_fandom_image(name)
        if image:
            return image, "Movie portrayal · Image via Harry Potter Wiki"
    except (requests.RequestException, ValueError):
        pass
    return None, None


spell_prompt = """
Find the spell from the Harry Potter books matching the user's search by its name or incantation. This includes charms, curses, jinxes, hexes, transfiguration, and other spells.

Respond with a JSON in the following format:

{
    "Spell": {
        "Name": "SPELL_NAME",
        "Incantation": "INCANTATION",
        "Type": "SPELL_TYPE",
        "Effect": "WHAT_THE_SPELL_DOES"
    },
    "Suggestions": []
}

Only return Spell for a matching name or incantation, ignoring capitalization. If the search is misspelled, return Spell as null and suggest up to five similar real spell names or incantations in Suggestions as a list of strings, best matches first. Consider missing letters, transposed letters, and similar-sounding words. For example, Lummos should suggest Lumos. Do not silently treat a misspelled incantation as an exact match. Leave Suggestions empty for an exact match or when no plausible similar spells exist.

Describe what the spell does clearly and concisely, using only information confirmed in the books. Do not invent spells, effects, incantations, or suggestions, or include movie-only or supplementary material. Use "Unknown" if the books do not give an incantation or classification. Return {"Spell": null, "Suggestions": []} if no book spell matches or is plausibly similar to the search.
"""


def get_spell(query):
    result = ask_model(spell_prompt, query)
    if not isinstance(result, dict) or "Spell" not in result:
        raise ValueError("Missing spell result")
    spell = result["Spell"]
    if spell is not None and (
        not isinstance(spell, dict)
        or not all(
            isinstance(spell.get(field), str) and spell[field].strip()
            for field in ("Name", "Incantation", "Type", "Effect")
        )
    ):
        raise ValueError("Invalid spell fields")
    suggestions = result.get("Suggestions")
    if not isinstance(suggestions, list) or not all(
        isinstance(name, str) and name.strip() for name in suggestions
    ):
        raise ValueError("Spell suggestions must contain names")
    return spell, suggestions


section = st.session_state.get("section", "home")
if section == "home":
    st.write("What would you like to explore?")
    st.button("Character Search", on_click=open_section, args=("characters",))
    st.button("Spell Book", on_click=open_section, args=("spells",))
    st.stop()

st.button("Back to start", on_click=open_section, args=("home",))

if section == "spells":
    st.header("Spell Book")
    with st.form("spell_lookup"):
        spell_query = st.text_input("Enter a spell name or incantation:", key="spell_search")
        spell_submitted = st.form_submit_button("Search spell")
    spell_requested = st.session_state.pop("spell_requested", False)
    if spell_submitted or spell_requested:
        query = spell_query.strip()
        if not query:
            st.warning("Enter a spell name or incantation to search.")
        else:
            st.session_state.pop("spell", None)
            st.session_state.pop("spell_suggestions", None)
            try:
                with st.spinner(f"Looking up {query}..."):
                    spell, suggestions = get_spell(query)
                if spell is not None:
                    st.session_state["spell"] = spell
                elif suggestions:
                    st.session_state["spell_suggestions"] = suggestions
                else:
                    st.warning(f"No book spell found matching or similar to {query}.")
            except (ValueError, TypeError):
                st.error("The spell information could not be read. Please try again.")
            except Exception:
                st.error("The spell search failed. Please try again or check your API access.")

    if "spell_suggestions" in st.session_state:
        st.write("No exact match. Did you mean:")
        for index, name in enumerate(st.session_state["spell_suggestions"]):
            st.button(
                name,
                key=f"spell_suggestion_{index}",
                on_click=select_spell_suggestion,
                args=(name,),
            )

    if "spell" in st.session_state:
        spell = st.session_state["spell"]
        st.subheader(spell["Name"])
        st.write("Incantation:", spell["Incantation"])
        st.write("Type:", spell["Type"])
        st.write("What it does:", spell["Effect"])
    st.stop()

with st.form("character_lookup"):
    user_prompt = st.text_input(
        "What Harry Potter Book character do you want to know about: ",
        key="character_search",
    )
    button = st.form_submit_button("Submit")
search_requested = st.session_state.pop("search_requested", False)
selected_match = st.session_state.pop("selected_match", None)

try:
    if button or search_requested:
        query = user_prompt.strip()
        if not query:
            st.warning("Enter a character name to search.")
        else:
            st.session_state.pop("temp", None)
            st.session_state.pop("matches", None)
            st.session_state.pop("matches_suggested", None)
            with st.spinner(f"Searching for {query}..."):
                matches, suggestions = find_matches(query)
            if not matches:
                if suggestions:
                    st.session_state["matches"] = suggestions
                    st.session_state["matches_suggested"] = True
                else:
                    st.warning(f"No book characters found matching or similar to {query}.")
            elif len(matches) == 1:
                selected_match = matches[0]
            else:
                st.session_state["matches"] = matches

    if selected_match:
        st.session_state.pop("temp", None)
        with st.spinner(f"Looking up {selected_match['Name']}..."):
            st.session_state["temp"] = get_character(selected_match)
except (ValueError, TypeError):
    st.error("The character information could not be read. Please try again.")
except Exception:
    st.error("The character search failed. Please try again or check your API access.")

if "matches" in st.session_state and "temp" not in st.session_state:
    if st.session_state.get("matches_suggested", False):
        st.write("No exact match. Did you mean:")
    else:
        st.write("Multiple characters match your search. Select one:")
    for index, match in enumerate(st.session_state["matches"]):
        st.button(
            f"{match['Name']} — {match['Description']}",
            key=f"match_{index}",
            on_click=select_match,
            args=(match,),
        )

if "temp" in st.session_state:
    if "matches" in st.session_state:
        st.button("Back to matches", on_click=back_to_matches)
    character = st.session_state["temp"]
    st.header(character["Name"])
    try:
        with st.spinner("Finding character image..."):
            character_image, caption = get_character_image(character["Name"])
    except (requests.RequestException, ValueError):
        character_image, caption = None, None

    if character_image:
        st.image(character_image, width=300, caption=caption)
    elif PLACEHOLDER_IMAGE.exists():
        st.image(str(PLACEHOLDER_IMAGE), width=300, caption="No movie portrait available · placeholder")
    else:
        st.caption("No movie image available for this character.")
    st.write("Species:", character["Species"])
    st.write("Blood Status:", character["Blood Status"])
    st.write("House:", character["House"])
    st.write("Special Abilities:")
    for ability in character["Special Abilities"]:
        st.markdown(f"- {ability}")
    if not character["Special Abilities"]:
        st.write("No special abilities identified in the books.")
    st.write("Aliases:")
    for alias in character["Aliases"]:
        st.markdown(f"- {alias}")
    if not character["Aliases"]:
        st.write("No aliases identified in the books.")
    st.write("Family:")
    for index, name in enumerate(character["Family"]):
        st.button(
            name,
            key=f"family_{index}_{name}",
            type="tertiary",
            on_click=select_family_member,
            args=(name,),
        )
