# Prenew Scout: set up your own Verda GPU server

Scout runs on your own computer, and you use it in your web browser. Its AI can run on a GPU server that you rent
from **Verda**, a European GPU cloud (formerly called DataCrunch). This guide takes you from nothing to Scout
searching with your own server.

- **Your time:** about 30 minutes of clicking and pasting, plus 30–60 minutes of waiting while the server
  downloads the AI model.
- **Cost:** Verda is prepaid. It deducts the server's hourly price every 10 minutes, from about €1.56 an hour
  (see Part 4.1). **A shut-down server still costs the full price.** To stop paying, *delete* the server and keep
  its disk (Part 6).
- **You need:** a Windows 10/11 PC or a Mac, and either an invitation to Prenew's Verda project or a payment card
  for your own Verda account.

> **Already have a server?** If a teammate runs a Scout GPU server and sent you its **Address** and **API key**,
> you don't need a Verda account. Do Part 1, then jump to Part 5.

**Contents**

1. Get Scout running on your computer
2. Get your Verda login
3. Make your SSH key (your login key for the server)
4. Rent the GPU server and install Scout's AI
5. Connect Scout to your server
6. Stop paying when you're not using it
7. If something goes wrong
8. Keep it safe

**Where to type commands.** Grey boxes are commands to copy and paste.

- **Windows:** open the Start menu, type **PowerShell** and open *Windows PowerShell*. Paste with **Ctrl+V** or a
  right-click, then press **Enter**.
- **Mac:** press **⌘ Space**, type **Terminal** and press **Enter**. Paste with **⌘ V**, then press **Enter**.

The same commands work on both unless a step says otherwise.

---

## Part 1: Get Scout running on your computer

*Skip this part if Scout already opens for you at http://localhost:8001.*

**1. Install Python 3.12**, the version Scout uses.

- Open https://www.python.org/downloads/release/python-31210/ and scroll down to **Files**.
- **Windows:** download **Windows installer (64-bit)** and run it. On the first screen, **tick "Add python.exe to
  PATH"** at the bottom, then click *Install Now*.
- **Mac:** download **macOS 64-bit universal2 installer** and run it. The Python that comes with macOS is too old
  for Scout.

**2. Download Scout.**

- Download https://github.com/tommy2006/prenewchocolate/archive/refs/heads/son.zip and unzip it (Windows:
  right-click the file → *Extract All*; Mac: double-click it). You get a folder called `prenewchocolate-son`.
  Move it somewhere permanent, such as Documents. This is **your Scout folder**.
- If you use Git, you can clone it instead:
  ```
  git clone --branch son https://github.com/tommy2006/prenewchocolate.git prenew-scout
  ```

**3. Start Scout.**

- **Windows:** in your Scout folder, double-click **`run.bat`**. If Windows shows a security warning (such as
  *"Windows protected your PC"*), click **More info → Run anyway**, or **Run**. It's Scout's start script.
- **Mac:** in Terminal, type `cd ` (with a space after it), drag your Scout folder onto the Terminal window and press
  **Enter**. Then run:
  ```
  bash run.sh
  ```

The first start installs what Scout needs and takes a few minutes. When the window shows
`Uvicorn running on http://127.0.0.1:8001`, open **http://localhost:8001** in your browser.

**Keep that window open** while you use Scout: closing it stops Scout. To stop Scout on purpose, click the window
and press **Ctrl+C**. On Windows, answer **Y** if it asks *"Terminate batch job (Y/N)?"*.

**Getting updates later.** Your settings and creators live in the `data` folder inside your Scout folder.

- **ZIP:** download the ZIP again, unzip it, and copy the `data` folder from your old Scout folder into the new one.
- **Git:** run `git pull` in your Scout folder, then install any new packages once:
  - Windows: `.venv\Scripts\python -m pip install -r requirements.txt`
  - Mac: `.venv/bin/pip install -r requirements.txt`

---

## Part 2: Get your Verda login

Everyone needs their own Verda login, because Verda's terms don't allow shared logins. There are two ways to get
one.

### Option A: join Prenew's Verda project (recommended)

The team's balance pays for your server, so you don't need a card.

1. Ask whoever manages Prenew's Verda project to invite your work email. That's probably the person who sent you this
   guide.
2. Open the invitation email from Verda and click the link.
3. If you're new to Verda, the link takes you to **Create an account**:
   - Enter the same email and a password.
   - Tick *I agree to the Terms and Conditions…* and click **Create account**.
   - Click the link in the *Verify your email* message, then **Continue to console**.
   - You land back on the invitation, and Verda shows *Project invitation accepted*.
4. In the project menu at the top of the sidebar, check that the team project is selected, not *My Project*.

As a *Developer* you can create and delete servers, but you can't add money. If Verda says *Project balance is too
low*, ask the project owner to top it up.

### Option B: your own account (you pay)

1. Go to https://console.verda.com/signin?signup. Enter your email and a password, tick *I agree to the Terms and
   Conditions…*, and click **Create account**.
2. Click the link in the verification email, then **Continue to console**.
3. Open **Billing** in the sidebar and fill in your billing details. Verda won't let you create a server until you
   do.
4. Add money. Either do a **One time top-up** (€30–50 is plenty to try things out) or set up an **Automatic top-up**.

> **Keep an eye on the balance.** Verda is prepaid. If the balance reaches zero, Verda removes your servers *and
> deletes their disks*. You can restore disks for 96 hours. Automatic top-up prevents this.

---

## Part 3: Make your SSH key

Verda servers don't use passwords. You log in with an **SSH key**, a pair of files on your computer. The *public*
half goes to Verda. The *private* half never leaves your computer, and you never send it to anyone.

**1. Create the key.** Run:

```
ssh-keygen -t ed25519
```

- Press **Enter** to accept the suggested file.
- Type a passphrase (a password for the key) and press **Enter**, twice. Or press **Enter** twice for no
  passphrase.
- If it says the file *already exists* and asks *"Overwrite (y/n)?"*, type **n**. You already have a key, so use
  that one.

**2. Show your public key.** Run:

```
cat ~/.ssh/id_ed25519.pub
```

It prints one line that starts with `ssh-ed25519`. Copy the whole line. Or copy it straight to the clipboard:

- Windows: `Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard`
- Mac: `pbcopy < ~/.ssh/id_ed25519.pub`

**3. Add it to Verda.**

1. In the console sidebar, open **Project management → Credentials**.
2. Under **SSH Keys**, click **+ Create**.
3. Paste the line into **Public key**, and give it a **Key name** such as *Anna's laptop*.
4. Click **Save SSH key**.

You can also add the key while creating the server, in its **SSH Keys** section → **Add new key**.

---

## Part 4: Rent the GPU server and install Scout's AI

### 4.1 Pick a size

Scout's setup script chooses the AI model by itself, based on the GPU memory. Prices are per hour as of September
2026, before VAT. Verda shows the exact price before you deploy.

| GPU | Per hour | AI model you get |
|---|---|---|
| **1× A100 SXM4 80GB** | €1.56 ($1.80) | Qwen3-30B-A3B, the cheapest option |
| **1× H100 SXM5 80GB** | €3.05 ($3.52) | Qwen3-30B-A3B, faster |
| **1× H200 SXM5 141GB** | €3.98 ($4.59) | Qwen3-30B-A3B, fastest |
| **2× H200 SXM5 141GB** | €7.96 ($9.19) | **Qwen3-235B-A22B**, the best at Finnish, German and Swedish |

- **Disk:** 150 GiB for a one-GPU server, 350 GiB for 2× H200.
- **Where to start:** a one-GPU server is enough to get going. Move to 2× H200 when you want the best results.
- **What won't work:** smaller GPUs, such as *A100 40GB*, *L40S* or *RTX A6000*. The script stops with
  *Need at least ~70 GB of GPU memory*.

### 4.2 Create the server

1. Go to the **Instances** page and click **Create instance**. Some of Verda's help pages call it
   *Deploy instance*.
2. **Instance Type:** choose **On-Demand**. *Spot* costs half as much, but Verda can delete a Spot server at any
   moment without warning.
3. **Contract:** choose **Pay As You Go**. Don't pick a long-term contract: those are paid up front and can't be
   cancelled.
4. **Compute configuration:** click the GPU from 4.1, then its size (**1x** or **2x**), then a location
   (*Finland 1*, *2* or *3*). A greyed-out size is sold out right now. Try another Finland location or another GPU
   from the table, or click **Notify me**.
5. **Main OS Volume:** keep **Create new**.
   - **Image:** an **Ubuntu 24.04** image **with CUDA**. Pick the highest CUDA version in the list, and not
     *Minimal*.
   - **Size:** **150**, or **350** for 2× H200. The default is too small for the AI model.
6. **SSH Keys:** tick **your** key. In a team project you'll see everyone's keys, so tick only yours. If your key
   isn't there yet, click **Add new key** and paste the line from Part 3.
7. **Startup Script:** leave it empty.
8. **Hostname:** for example `scout-anna`. You can't change it later.
9. Check the price in the **Deployment Summary**, then click **Deploy now**. If your balance needs a top-up first,
   the button is **Pay now & Deploy** instead.
10. Wait a few minutes until the server is running. Then copy its **IP** address from the Instances list (click the
    copy icon).

There's no firewall to set up. Verda doesn't filter ports, which is why the next step protects the AI with a key.

### 4.3 Install Scout's AI on the server

Keep your computer plugged in and awake for the next hour. Then, in PowerShell or Terminal, run this command.
First replace `SERVER-IP` with your server's IP address, and keep the quotes:

```
ssh root@SERVER-IP "curl -fsSL https://raw.githubusercontent.com/tommy2006/prenewchocolate/son/scripts/verda_setup.sh -o verda_setup.sh && bash verda_setup.sh"
```

- The first time, ssh asks *"Are you sure you want to continue connecting (yes/no/[fingerprint])?"*. Type
  **yes** and press **Enter**.
- If you gave your key a passphrase, type it when asked.
- Then wait. The script installs the AI server software (vLLM) and downloads the model. The large model takes 10–30
  minutes to download. The script then loads the model onto the GPUs, which takes another 3–10 minutes.
  Altogether it's usually 20–40 minutes.
- **If the connection drops** (Wi-Fi, or your computer went to sleep), run the same command again. It continues
  where it stopped and keeps what it already downloaded.

When it's done, the end of the output looks like this (with your own numbers):

```
Ready. Test answer: Hei

In Scout: Settings -> Search AI -> "Your GPU server"
  Address:  http://203.0.113.10:8000/v1
  API key:  9f2c...(48 letters and digits)
  Model:    scout
```

- Save the **Address** and **API key** somewhere safe, such as a password manager. You need them in Part 5.
- You can ignore the script's tip about opening port 8000 in the Verda console. Verda doesn't filter ports.

> **Why download the script on the server?** Scout's README says to copy `scripts/verda_setup.sh` from your Scout
> folder with `scp`. On Windows, that copy can end up with Windows line endings, and Linux then refuses to run it
> (`set: pipefail^M: invalid option name`). Downloading it straight from GitHub on the server always works.

---

## Part 5: Connect Scout to your server

1. Open Scout at **http://localhost:8001** and click the **gear icon** (Settings) in the top bar.
2. Under **Search AI**, click the **Your GPU server** card.
3. Paste your **Address** into the **Address** box first. It looks like `http://203.0.113.10:8000/v1`.
4. Then paste your **API key** into **API key (if the server needs one)**. Scout checks the server straight away.
   You should see **✓ 1 models available. Using scout.** and then
   **✓ Connected: Your GPU server (scout) answers in the right format**.
   If you pasted the key before the address, you'll see an error instead. Press **Test Your GPU server** once both
   boxes are filled in.
5. **Model** should show `scout`. If it's empty, press **Load models**.
6. Under **Writing AI**, leave **Same as the search AI (Your GPU server)**. This one is optional: a paid AI such as
   OpenAI or Gemini writes better Finnish and German outreach messages, for about a cent per message.
7. Under **Data sources**, add a **YouTube API key** if you want YouTube creators. It's free: in the Google Cloud
   console, enable *YouTube Data API v3*, then go to *Credentials* → *Create API key*. TikTok needs nothing, and
   Twitch is optional.
8. Press **Save**. Scout confirms: *Saved. Searches use Your GPU server (scout); messages use Your GPU server.*

---

## Part 6: Stop paying when you're not using it

**Shutdown doesn't save money.** A shut-down server still costs its full hourly price. To stop paying for the GPU,
*delete* the server and keep its disk. The disk holds the AI model and your API key, so you can come back later
without installing anything again.

### Pause: delete the server, keep the disk

1. On the **Instances** page, open your server's menu (the gear icon on its row, or **Actions** on its page) and
   choose **Delete instance**.
2. Under **Choose storage to delete**, leave everything **unticked**. Your disk is kept.
3. Click **Delete**.

A kept disk costs about $0.20 per GiB per month. That's about $30 a month for 150 GiB, or $70 for 350 GiB.

### Come back later

1. Click **Create instance**. Pick the **same GPU and size** as before, in the **same location** as your disk.
2. Under **Main OS Volume**, choose **Use existing** and pick your old disk. Your SSH key comes with it.
3. Click **Deploy now**. The AI starts by itself: give it 5–10 minutes to load onto the GPUs. There's nothing to
   install.
4. The server has a **new IP address**, so update Scout:
   - Open Settings → **Your GPU server**.
   - Change the **Address** to `http://NEW-IP:8000/v1`.
   - Press **Test Your GPU server**, then **Save**.
   - The API key stays the same.

If that GPU is sold out in your disk's location, you can wait. Or start fresh: create a new server (Part 4.2) and
run the install command again (Part 4.3). Starting fresh downloads the model again and gives you a new API key.

### Done for good

Choose **Delete instance**, and this time **tick** the disk. You can restore a deleted disk for 96 hours; after
that it's gone.

---

## Part 7: If something goes wrong

**Starting Scout on your computer**

| What you see | What to do |
|---|---|
| Windows: `'python' is not recognized`, or the Microsoft Store opens | Python isn't installed, or isn't on PATH. Run the Python installer again, choose *Modify* or *Repair*, and make sure **Add python.exe to PATH** is ticked. |
| Mac: errors about `int \| None`, or `python3 --version` shows 3.9 | You're using macOS's old Python. Install Python 3.12 (Part 1), open a new Terminal window, and run `bash run.sh` again. |
| `address already in use`, or `error while attempting to bind` on port 8001 | Scout is already running in another window. Use that one, or close it first. |

**In the Verda console**

| What you see | What to do |
|---|---|
| *Not enough available resources*, or *The selected compute is not available at this time* | That GPU is sold out. Try another Finland location or another GPU from Part 4.1, or try again later. |
| *Quota limit reached* | The account needs a higher limit. In a team project, that's the owner's account. Open **Account settings → Quotas** and click **Request increase**. Verda answers in about a business day. |
| *Project owner must add billing details*, or *Project balance is too low* | Own account: fill in **Billing** or top up. Team project: ask the project owner. |
| The server is still starting after 20 minutes | Contact Verda support with your Project ID and Instance ID. Use the chat icon at the bottom right of the console, or email support@verda.com. |

**Connecting to the server**

| What you see | What to do |
|---|---|
| Windows: `ssh` or `ssh-keygen` is not recognized | Open **Settings → System → Optional features**, add **OpenSSH Client**, then open a new PowerShell window. |
| `Permission denied (publickey)` | The server doesn't have your key. Verda only adds keys when it creates the server. Check that you ticked your key and that you log in as `root`. If you didn't tick it, delete the server (tick its disk too) and create it again. |
| `Connection timed out` or `Connection refused` | The server is still starting (wait a minute), or the IP address is wrong. |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED` | Verda gave your new server an IP address you've used before. Run `ssh-keygen -R SERVER-IP`, then connect again. |

**Installing the AI**

| What you see | What to do |
|---|---|
| `No NVIDIA driver (nvidia-smi) found` | The server has the wrong image. Delete it (tick its disk) and create it again with an Ubuntu 24.04 + CUDA image (Part 4.2). |
| `Need at least ~70 GB of GPU memory and ~75 GB of free disk` | The GPU or the disk is too small. Delete the server (tick its disk) and create it again with a size from Part 4.1. |
| `The service stopped. Last log lines:` | Send those lines to the person who shared this guide with you. |

**Scout can't use the server**

| What you see | What to do |
|---|---|
| `Can't reach http://…/v1`, or `Can't connect to http://…/v1` | The server is off or was deleted, or the AI is still loading (allow 5–10 minutes after the server starts). Or the Address is wrong: it must end in `:8000/v1`. |
| `Your GPU server rejected the API key`, or `error 401` | Paste the API key again, with no spaces before or after it. |
| You lost the API key | Run `ssh root@SERVER-IP "cat /opt/scout-ai/api_key"`. The Address is always `http://SERVER-IP:8000/v1`. |
| You want to see what the AI server is doing | Run `ssh root@SERVER-IP "journalctl -u scout-ai -n 50 --no-pager"`. |

---

## Part 8: Keep it safe

- **The API key is the password to a server you pay for.** Don't post it in shared channels, documents or
  screenshots. To share your server with a teammate, send them the Address and key privately. One server can serve
  several people at once, but they share its speed, and the cost stays on your Verda balance.
- **The connection isn't encrypted.** The key keeps other people out, but the traffic travels as plain HTTP. For
  an encrypted connection (advanced), install with `PUBLIC=0`:
  ```
  ssh root@SERVER-IP "curl -fsSL https://raw.githubusercontent.com/tommy2006/prenewchocolate/son/scripts/verda_setup.sh -o verda_setup.sh && PUBLIC=0 bash verda_setup.sh"
  ```
  Then keep this running in its own window while you use Scout:
  ```
  ssh -N -L 8008:localhost:8000 root@SERVER-IP
  ```
  In Scout, use the Address `http://localhost:8008/v1`.
- **Your Verda login is yours.** In a team project, everyone can see and delete everyone's servers. Name yours
  clearly, for example `scout-anna`, and only touch your own.
- **When you stop working on Scout**, delete your server and tick its disk (Part 6).
