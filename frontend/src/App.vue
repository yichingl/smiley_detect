<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
  }

  interface TaskInfo {
    guid: string
    detection_count: number
    task_status: string
    model_name?: string | null
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  interface DatasetImage {
    name: string
    image_url: string
    detection_count: number
  }

  interface ModelEpoch {
    epoch: number
    train_box_loss: number
    val_box_loss: number
    precision: number
    recall: number
    map50: number
    map50_95: number
  }

  interface ModelRun {
    name: string
    note: string | null
    available: boolean
    best_epoch: number | null
    epochs: ModelEpoch[]
  }

  const readCachedModelRuns = (): ModelRun[] => {
    try {
      const cachedModels = localStorage.getItem('smiley-model-runs')
      const parsedModels: unknown = cachedModels ? JSON.parse(cachedModels) : []
      return Array.isArray(parsedModels)
        ? parsedModels.filter((run): run is ModelRun =>
            typeof run?.name === 'string' &&
            Array.isArray(run.epochs) &&
            typeof run.available === 'boolean' &&
            (typeof run.best_epoch === 'number' || run.best_epoch === null)
          )
        : []
    } catch (err) {
      console.warn('Could not read cached model runs:', err)
      return []
    }
  }

  const readSelectedModel = () => {
    try {
      return localStorage.getItem('smiley-selected-model') || ''
    } catch (err) {
      console.warn('Could not read selected model:', err)
      return ''
    }
  }

  const writeBrowserCache = (key: string, value: string) => {
    try {
      localStorage.setItem(key, value)
    } catch (err) {
      console.warn(`Could not save ${key} in browser storage:`, err)
    }
  }

  // variables
  const activeTab = ref<'home' | 'validation' | 'training' | 'models'>('home')
  const images = ref<InferenceImage[]>([])
  const modelRuns = ref<ModelRun[]>(readCachedModelRuns())
  const selectedModel = ref(
    readSelectedModel() || modelRuns.value.find((run) => run.available)?.name || ''
  )
  const isModelPickerOpen = ref(false)
  const isLoadingModels = ref(false)
  const modelsError = ref('')
  const modelsLoaded = ref(false)
  const validationImages = ref<DatasetImage[]>([])
  const trainingImages = ref<DatasetImage[]>([])
  const isLoadingValidationImages = ref(false)
  const isLoadingTrainingImages = ref(false)
  const validationImagesError = ref('')
  const trainingImagesError = ref('')
  const validationImagesLoaded = ref(false)
  const trainingImagesLoaded = ref(false)
  const activeDatasetSplit = computed(() => activeTab.value === 'training' ? 'training' : 'validation')
  const activeDatasetImages = computed(() =>
    activeDatasetSplit.value === 'training' ? trainingImages.value : validationImages.value
  )
  const isLoadingDatasetImages = computed(() =>
    activeDatasetSplit.value === 'training' ? isLoadingTrainingImages.value : isLoadingValidationImages.value
  )
  const datasetImagesError = computed(() =>
    activeDatasetSplit.value === 'training' ? trainingImagesError.value : validationImagesError.value
  )
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, TaskInfo[]>>({})

  // Track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // Upload state variables
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFile = ref<File | null>(null)
  const isUploading = ref(false)
  const uploadMessage = ref('')

  // Fetch existing uploaded images on mount / refresh
  const fetchImages = async () => {
    try {
      const response = await fetch('/images')
      if (response.ok) {
        images.value = await response.json()
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    }
  }

  const fetchModels = async () => {
    isLoadingModels.value = true
    modelsError.value = ''

    try {
      const response = await fetch('/models')
      if (!response.ok) {
        throw new Error(`Models request failed with status ${response.status}`)
      }

      const data = await response.json()
      modelRuns.value = data.runs || []
      writeBrowserCache('smiley-model-runs', JSON.stringify(modelRuns.value))
      const selectedModelExists = modelRuns.value.some(
        (run) => run.name === selectedModel.value && run.available
      )
      if (!selectedModelExists) {
        selectedModel.value = modelRuns.value.find((run) => run.available)?.name || ''
        writeBrowserCache('smiley-selected-model', selectedModel.value)
      }
      modelsLoaded.value = true
    } catch (err) {
      modelsError.value = 'Could not load model runs. Please try again.'
      console.error('Failed to fetch model runs:', err)
      if (modelRuns.value.length === 0) {
        modelsLoaded.value = false
      }
    } finally {
      isLoadingModels.value = false
    }
  }

  const formatMetric = (value: number) => value.toFixed(4)

  const getBestEpoch = (run: ModelRun) =>
    run.epochs.find((epoch) => epoch.epoch === run.best_epoch)

  const getBestEpochRows = (run: ModelRun) => {
    const epoch = getBestEpoch(run)
    return epoch ? [epoch] : []
  }

  const chooseModel = (modelName: string) => {
    selectedModel.value = modelName
    writeBrowserCache('smiley-selected-model', modelName)
    isModelPickerOpen.value = false
  }

  const openModelPicker = async () => {
    isModelPickerOpen.value = true
    if (modelRuns.value.length === 0 && !isLoadingModels.value) {
      await fetchModels()
    }
  }

  const fetchDatasetImages = async (split: 'training' | 'validation', refresh = false) => {
    const loading = split === 'training' ? isLoadingTrainingImages : isLoadingValidationImages
    const error = split === 'training' ? trainingImagesError : validationImagesError
    const loaded = split === 'training' ? trainingImagesLoaded : validationImagesLoaded
    const datasetImages = split === 'training' ? trainingImages : validationImages
    loading.value = true
    error.value = ''

    try {
      const response = await fetch(`/${split}-images${refresh ? '?refresh=true' : ''}`)
      if (!response.ok) {
        throw new Error(`${split} images request failed with status ${response.status}`)
      }

      const data = await response.json()
      datasetImages.value = data.images || []
      loaded.value = true
    } catch (err) {
      error.value = `Could not load ${split} images. Please try again.`
      console.error(`Failed to fetch ${split} images:`, err)
    } finally {
      loading.value = false
    }
  }

  const selectTab = async (tab: 'home' | 'validation' | 'training' | 'models') => {
    activeTab.value = tab
    if (tab === 'models' && !modelsLoaded.value && !isLoadingModels.value) {
      await fetchModels()
    } else if (
      (tab === 'training' || tab === 'validation') &&
      !(tab === 'training' ? trainingImagesLoaded.value : validationImagesLoaded.value)
    ) {
      await fetchDatasetImages(tab)
    }
  }

  // Handle file selection
  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (target.files && target.files[0]) {
      selectedFile.value = target.files[0]
    }
  }

  // Upload single image via /upload-single-image/
  const uploadImage = async () => {
    if (!selectedFile.value) {
      uploadMessage.value = 'Please select a file first!'
      return
    }

    const formData = new FormData()
    formData.append('file', selectedFile.value)

    isUploading.value = true
    uploadMessage.value = ''

    try {
      const response = await fetch('/upload-single-image/', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      uploadMessage.value = 'Image uploaded successfully!'
      selectedFile.value = null
      if (fileInput.value) fileInput.value.value = ''

      // Refresh images list automatically after upload
      await fetchImages()
    } catch (err) {
      uploadMessage.value = 'Error uploading image. Please try again.'
      console.error(err)
    } finally {
      isUploading.value = false
    }
  }

  // Fetch tasks for a specific image GUID (used for initial expansion and manual refresh)
  const fetchTasksForImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/images/${imgGuid}/tasks`)
      if (response.ok) {
        const data = await response.json()
        imageDetails.value[imgGuid] = data.tasks || []
      } else {
        imageDetails.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch tasks for image', err)
      imageDetails.value[imgGuid] = []
    }
  }

  // Toggle expansion and lazily fetch tasks if not loaded yet
  const toggleExpand = async (img: InferenceImage) => {
    const currentState = !!expandedImages.value[img.guid]
    expandedImages.value[img.guid] = !currentState

    if (!currentState && !imageDetails.value[img.guid]) {
      await fetchTasksForImage(img.guid)
    }
  }

  // Start a task for the image guid
  const startTaskOnImage = async (imgGuid: string) => {
    if (!selectedModel.value) {
      isModelPickerOpen.value = true
      return
    }

    try {
      const response = await fetch(`/process-image/${imgGuid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: selectedModel.value })
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `Server returned status ${response.status}`)
      }
      // Automatically refresh tasks list after starting a new task
      await fetchTasksForImage(imgGuid)
    } catch (err) {
      console.error('Failed to start processing on image:', err)
    }
  }

  // Fetch task details and detections when a task item is clicked
  const selectTaskAndFetchDetections = async (imgGuid: string, task: TaskInfo) => {
    activeTaskId.value[imgGuid] = task.guid
    try {
      const response = await fetch(`/task-details/${task.guid}`)
      if (response.ok) {
        const data = await response.json()
        activeDetections.value[imgGuid] = data.detections || []
      } else {
        activeDetections.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch task detections:', err)
      activeDetections.value[imgGuid] = []
    }
  }

  onMounted(() => {
    fetchImages()
    fetchModels()
  })
</script>

<template>
  <main class="dashboard">
    <div class="dashboard__shell">
      <header class="page-header">
        <div class="brand-mark" aria-hidden="true">S</div>
        <div class="page-header__copy">
          <p class="eyebrow">IMAGE ANALYSIS</p>
          <h1>Smiley Detection</h1>
          <p class="page-header__subtitle">Upload images, run detection, and review your results.</p>
        </div>
        <div class="image-count" aria-live="polite">
          <span class="image-count__value">{{ images.length }}</span>
          <span>{{ images.length === 1 ? 'image' : 'images' }} in library</span>
        </div>
      </header>

      <nav class="tab-nav" aria-label="Main navigation">
        <button
          class="tab-nav__button"
          :class="{ 'tab-nav__button--active': activeTab === 'home' }"
          type="button"
          :aria-current="activeTab === 'home' ? 'page' : undefined"
          @click="selectTab('home')"
        >
          Home
        </button>
        <button
          class="tab-nav__button"
          :class="{ 'tab-nav__button--active': activeTab === 'validation' }"
          type="button"
          :aria-current="activeTab === 'validation' ? 'page' : undefined"
          @click="selectTab('validation')"
        >
          Validation Data
        </button>
        <button
          class="tab-nav__button"
          :class="{ 'tab-nav__button--active': activeTab === 'training' }"
          type="button"
          :aria-current="activeTab === 'training' ? 'page' : undefined"
          @click="selectTab('training')"
        >
          Training Data
        </button>
        <button
          class="tab-nav__button"
          :class="{ 'tab-nav__button--active': activeTab === 'models' }"
          type="button"
          :aria-current="activeTab === 'models' ? 'page' : undefined"
          @click="selectTab('models')"
        >
          Models
        </button>
      </nav>

      <section class="selected-model" aria-label="Selected detection model">
        <div>
          <p class="eyebrow">SELECTED MODEL</p>
          <strong>{{ selectedModel || 'No model selected' }}</strong>
        </div>
        <button class="button button--secondary" type="button" @click="openModelPicker">
          Edit
        </button>
      </section>

      <div v-if="activeTab === 'home'">
      <section class="panel upload-panel" aria-labelledby="upload-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">GET STARTED</p>
            <h2 id="upload-heading">Add an image</h2>
            <p class="section-description">Choose a JPG or PNG image to run smiley detection.</p>
          </div>
          <span class="upload-icon" aria-hidden="true">↑</span>
        </div>

        <div class="upload-controls">
          <label class="file-picker" :class="{ 'file-picker--selected': selectedFile }">
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg, image/jpg, image/png"
              @change="handleFileChange"
            />
            <span class="file-picker__icon" aria-hidden="true">＋</span>
            <span class="file-picker__text">
              <strong>{{ selectedFile ? selectedFile.name : 'Choose an image' }}</strong>
              <small>{{ selectedFile ? 'Ready to upload' : 'JPG or PNG, select a file from your device' }}</small>
            </span>
            <span class="file-picker__action">Browse</span>
          </label>
          <button
            class="button button--primary upload-button"
            type="button"
            :disabled="isUploading || !selectedFile"
            @click="uploadImage"
          >
            <span v-if="isUploading" class="button-spinner" aria-hidden="true"></span>
            {{ isUploading ? 'Uploading' : 'Upload image' }}
          </button>
        </div>

        <p
          v-if="uploadMessage"
          class="feedback-message"
          :class="uploadMessage.includes('successfully') ? 'feedback-message--success' : 'feedback-message--error'"
          role="status"
        >
          {{ uploadMessage }}
        </p>
      </section>

      <section class="library-section" aria-labelledby="library-heading">
        <div class="library-heading">
          <div>
            <p class="eyebrow">YOUR WORKSPACE</p>
            <h2 id="library-heading">Image library</h2>
            <p class="section-description">Select an image to inspect it and manage detection tasks.</p>
          </div>
          <button class="button button--secondary" type="button" @click="fetchImages">
            <span aria-hidden="true">↻</span>
            Refresh
          </button>
        </div>

        <div v-if="images.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>Your library is empty</h3>
          <p>Upload an image above to get started. Your images and detection tasks will appear here.</p>
        </div>

        <div v-else class="image-list">
          <article v-for="img in images" :key="img.guid" class="image-card">
            <div class="image-card__summary">
              <button
                class="image-card__toggle"
                type="button"
                :aria-expanded="!!expandedImages[img.guid]"
                @click="toggleExpand(img)"
              >
                <img class="image-card__thumbnail" :src="`/${img.filepath}`" :alt="`Thumbnail of ${img.name}`" />
                <span class="image-card__details">
                  <strong class="image-card__name">{{ img.name }}</strong>
                  <span class="image-card__path">{{ img.filepath }}</span>
                </span>
                <span class="image-card__chevron" :class="{ 'image-card__chevron--expanded': expandedImages[img.guid] }" aria-hidden="true">
                  ⌄
                </span>
              </button>
              <span class="image-card__task-count">
                {{ imageDetails[img.guid]?.length ?? 0 }}
                {{ imageDetails[img.guid]?.length === 1 ? 'task' : 'tasks' }}
              </span>
            </div>

            <div v-if="expandedImages[img.guid]" class="image-card__content">
              <div class="image-overview">
                <div class="preview-frame">
                  <img
                    class="preview-frame__image"
                    :src="activeTaskId[img.guid] ? `/tasks/${activeTaskId[img.guid]}/rendered-image` : `/${img.filepath}`"
                    :alt="activeTaskId[img.guid] ? `Detection result for ${img.name}` : `Preview of ${img.name}`"
                  />
                  <span
                    v-if="activeTaskId[img.guid] && activeDetections[img.guid]?.length === 0"
                    class="preview-frame__badge"
                  >
                    No smileys detected
                  </span>
                </div>

                <div class="image-metadata">
                  <div class="image-metadata__heading">
                    <div>
                      <p class="eyebrow">IMAGE DETAILS</p>
                      <h3>{{ img.name }}</h3>
                    </div>
                    <button class="button button--primary" type="button" @click="startTaskOnImage(img.guid)">
                      Run detection
                    </button>
                  </div>
                  <dl class="metadata-list">
                    <div>
                      <dt>Uploaded</dt>
                      <dd>{{ img.uploaded_at ? new Date(img.uploaded_at).toLocaleString() : '--' }}</dd>
                    </div>
                    <div>
                      <dt>Image ID</dt>
                      <dd class="metadata-list__id">{{ img.guid }}</dd>
                    </div>
                    <div>
                      <dt>Upload group</dt>
                      <dd class="metadata-list__id">{{ img.upload_group_id }}</dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div class="task-section">
                <div class="task-section__heading">
                  <div>
                    <h3>Detection tasks</h3>
                    <p class="section-description">Choose a task to view its result.</p>
                  </div>
                  <button class="button button--text" type="button" @click="fetchTasksForImage(img.guid)">
                    <span aria-hidden="true">↻</span>
                    Refresh tasks
                  </button>
                </div>

                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="task-empty">
                  No tasks yet. Run detection to create the first task.
                </div>
                <ul v-else class="task-list">
                  <li v-for="task in imageDetails[img.guid]" :key="task.guid">
                    <button
                      class="task-row"
                      :class="{ 'task-row--active': activeTaskId[img.guid] === task.guid }"
                      type="button"
                      :aria-pressed="activeTaskId[img.guid] === task.guid"
                      @click="selectTaskAndFetchDetections(img.guid, task)"
                    >
                      <span class="task-row__main">
                        <span class="task-row__id">{{ task.guid }}</span>
                        <span class="task-row__model">{{ task.model_name || 'Model not recorded' }}</span>
                      </span>
                      <span class="task-row__metrics">
                        <span class="status-badge" :class="`status-badge--${task.task_status.toLowerCase()}`">
                          {{ task.task_status }}
                        </span>
                        <span class="detection-count">
                          <strong>{{ task.detection_count }}</strong>
                          {{ task.detection_count === 1 ? 'detection' : 'detections' }}
                        </span>
                      </span>
                    </button>
                  </li>
                </ul>
              </div>
            </div>
          </article>
        </div>
      </section>
      </div>

      <section v-else-if="activeTab !== 'models'" class="validation-section" aria-labelledby="dataset-heading">
        <div class="library-heading">
          <div>
            <p class="eyebrow">{{ activeDatasetSplit === 'training' ? 'MODEL TRAINING' : 'MODEL VALIDATION' }}</p>
            <h2 id="dataset-heading">{{ activeDatasetSplit === 'training' ? 'Training Data' : 'Validation Data' }}</h2>
            <p class="section-description">
              {{ activeDatasetSplit === 'training' ? 'Training' : 'Validation' }} images with their annotated bounding boxes.
            </p>
            <p class="validation-disclaimer">
              These boxes are drawn from the dataset’s ground-truth label files. They are not model predictions.
            </p>
          </div>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isLoadingDatasetImages"
            @click="fetchDatasetImages(activeDatasetSplit, true)"
          >
            <span aria-hidden="true">↻</span>
            Refresh
          </button>
        </div>

        <div v-if="isLoadingDatasetImages" class="validation-loading" role="status" aria-live="polite">
          <span class="validation-spinner" aria-hidden="true"></span>
          <span>Preparing {{ activeDatasetSplit }} images…</span>
        </div>

        <div v-else-if="datasetImagesError" class="validation-error" role="alert">
          <p>{{ datasetImagesError }}</p>
          <button class="button button--secondary" type="button" @click="fetchDatasetImages(activeDatasetSplit)">
            Try again
          </button>
        </div>

        <div v-else-if="activeDatasetImages.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>No {{ activeDatasetSplit }} images found</h3>
          <p>Place JPG or PNG files and matching YOLO label files in the {{ activeDatasetSplit }} dataset.</p>
        </div>

        <div v-else class="validation-grid">
          <article v-for="img in activeDatasetImages" :key="img.name" class="validation-card">
            <div class="validation-card__image">
              <img
                :src="img.image_url"
                :alt="`Ground-truth bounding boxes for ${img.name}`"
                loading="lazy"
                decoding="async"
              />
            </div>
            <div class="validation-card__details">
              <h3>{{ img.name }}</h3>
              <span class="detection-count">
                <strong>{{ img.detection_count }}</strong>
                {{ img.detection_count === 1 ? 'detection' : 'detections' }}
              </span>
            </div>
          </article>
        </div>
      </section>

      <section v-else class="models-section" aria-labelledby="models-heading">
        <div class="library-heading">
          <div>
            <p class="eyebrow">TRAINING HISTORY</p>
            <h2 id="models-heading">Model runs</h2>
            <p class="section-description">Training and validation metrics for each saved run.</p>
          </div>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isLoadingModels"
            @click="fetchModels"
          >
            <span aria-hidden="true">↻</span>
            Refresh
          </button>
        </div>

        <div v-if="isLoadingModels" class="validation-loading" role="status" aria-live="polite">
          <span class="validation-spinner" aria-hidden="true"></span>
          <span>Loading model runs…</span>
        </div>

        <div v-else-if="modelsError" class="validation-error" role="alert">
          <p>{{ modelsError }}</p>
          <button class="button button--secondary" type="button" @click="fetchModels">
            Try again
          </button>
        </div>

        <div v-else-if="modelRuns.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>No model runs found</h3>
          <p>Saved training runs with results.csv files will appear here.</p>
        </div>

        <div v-else class="model-run-list">
          <article v-for="run in modelRuns" :key="run.name" class="model-run">
            <header class="model-run__header">
              <div class="model-run__title">
                <h3 :title="run.note || undefined">{{ run.name }}</h3>
                <span v-if="run.best_epoch !== null" class="model-run__best">
                  Best - Epoch {{ run.best_epoch }}
                </span>
              </div>
              <span class="model-run__epoch-count">{{ run.epochs.length }} epochs</span>
            </header>
            <div v-if="run.epochs.length === 0" class="task-empty">
              No epoch metrics found for this run.
            </div>
            <div v-else class="model-run__table-wrap">
              <table class="model-run__table">
                <thead>
                  <tr>
                    <th scope="col">Epoch</th>
                    <th scope="col">Train box</th>
                    <th scope="col">Validation box</th>
                    <th scope="col">Precision</th>
                    <th scope="col">Recall</th>
                    <th scope="col">mAP50</th>
                    <th scope="col">mAP50–95</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="epoch in run.epochs"
                    :key="epoch.epoch"
                    :class="{ 'model-run__best-row': epoch.epoch === run.best_epoch }"
                  >
                    <th scope="row">{{ epoch.epoch }}</th>
                    <td>{{ formatMetric(epoch.train_box_loss) }}</td>
                    <td>{{ formatMetric(epoch.val_box_loss) }}</td>
                    <td>{{ formatMetric(epoch.precision) }}</td>
                    <td>{{ formatMetric(epoch.recall) }}</td>
                    <td>{{ formatMetric(epoch.map50) }}</td>
                    <td>{{ formatMetric(epoch.map50_95) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </section>

      <footer class="page-footer">Smiley Detection <span aria-hidden="true">·</span> Image analysis workspace</footer>
    </div>

    <div
      v-if="isModelPickerOpen"
      class="model-picker-backdrop"
      role="presentation"
      @click.self="isModelPickerOpen = false"
    >
      <section
        class="model-picker"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-picker-heading"
      >
        <header class="model-picker__header">
          <div>
            <p class="eyebrow">INFERENCE SETTINGS</p>
            <h2 id="model-picker-heading">Select a model</h2>
            <p class="section-description">Choose a saved training run. Metrics shown are from its best.pt checkpoint.</p>
          </div>
          <button
            class="model-picker__close"
            type="button"
            aria-label="Close model picker"
            @click="isModelPickerOpen = false"
          >
            ×
          </button>
        </header>

        <div v-if="modelRuns.length === 0" class="task-empty">
          No saved models are cached yet. Check the Models tab or retry loading the model list.
        </div>
        <div v-else class="model-picker__runs">
          <article v-for="run in modelRuns" :key="run.name" class="model-picker__run">
            <div class="model-picker__run-heading">
              <div class="model-run__title">
                <h3 :title="run.note || undefined">{{ run.name }}</h3>
                <span v-if="run.best_epoch !== null" class="model-run__best">
                  Best - Epoch {{ run.best_epoch }}
                </span>
                <p v-if="!run.available" class="model-picker__unavailable">
                  No best.pt checkpoint is available for this run.
                </p>
              </div>
              <button
                class="button"
                :class="selectedModel === run.name ? 'button--primary' : 'button--secondary'"
                type="button"
                :disabled="!run.available"
                @click="chooseModel(run.name)"
              >
                {{ selectedModel === run.name ? 'Selected' : 'Use this model' }}
              </button>
            </div>
            <div v-if="getBestEpoch(run)" class="model-run__table-wrap">
              <table class="model-run__table">
                <thead>
                  <tr>
                    <th scope="col">Epoch</th>
                    <th scope="col">Train box</th>
                    <th scope="col">Validation box</th>
                    <th scope="col">Precision</th>
                    <th scope="col">Recall</th>
                    <th scope="col">mAP50</th>
                    <th scope="col">mAP50–95</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="epoch in getBestEpochRows(run)"
                    :key="epoch.epoch"
                    class="model-run__best-row"
                  >
                    <th scope="row">{{ epoch.epoch }}</th>
                    <td>{{ formatMetric(epoch.train_box_loss) }}</td>
                    <td>{{ formatMetric(epoch.val_box_loss) }}</td>
                    <td>{{ formatMetric(epoch.precision) }}</td>
                    <td>{{ formatMetric(epoch.recall) }}</td>
                    <td>{{ formatMetric(epoch.map50) }}</td>
                    <td>{{ formatMetric(epoch.map50_95) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </section>
    </div>
  </main>
</template>