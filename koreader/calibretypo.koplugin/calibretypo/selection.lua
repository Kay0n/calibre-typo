local logger = require("logger")

local Selection = {}

function Selection.fromHighlight(highlight, index)
    local source = highlight.selected_text
    if not source and index and highlight.ui.annotation then
        source = highlight.ui.annotation.annotations[index]
    end
    if not source or not source.text or source.text == "" then
        return nil
    end
    return { text = source.text, pos0 = source.pos0, pos1 = source.pos1 }
end

local function textBetween(document, from, to)
    local text = document:getTextFromXPointers(from, to)
    if type(text) == "table" then
        text = text.text
    end
    return text or ""
end

-- Lets the server place a selection that appears more than once
function Selection.context(document, pos0, pos1, words)
    local ok, before, after = pcall(function()
        local start, finish = pos0, pos1
        for _ = 1, words do
            local previous = document:getPrevVisibleWordStart(start)
            if not previous or previous == start then break end
            start = previous
        end
        for _ = 1, words do
            local following = document:getNextVisibleWordEnd(finish)
            if not following or following == finish then break end
            finish = following
        end
        return textBetween(document, start, pos0), textBetween(document, pos1, finish)
    end)
    if not ok then
        logger.warn("calibretypo: couldn't read the surrounding text:", before)
        return "", ""
    end
    return before, after
end

function Selection.bookInfo(ui)
    local props = ui.doc_props or {}
    local ok, raw = pcall(function() return ui.document:getProps() end)
    if not ok or type(raw) ~= "table" then
        raw = {}
    end
    local identifiers = props.identifiers or raw.identifiers
    if type(identifiers) == "table" then
        identifiers = table.concat(identifiers, "\n")
    end
    return {
        title = props.title or raw.title or props.display_title,
        authors = props.authors or raw.authors,
        identifiers = identifiers,
        filename = ui.document.file,
    }
end

return Selection
