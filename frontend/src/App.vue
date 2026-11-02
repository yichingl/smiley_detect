<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
    task_count: number
    saved_status?: 0 | 1 | 2
    saved_split?: 'training' | 'validation' | null
  }

  interface TaskInfo {
    guid: string
    detection_count: number
    task_status: string
    model_name?: string | null
    saved: 0 | 1 | 2
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  interface BoxCoordinates {
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  interface DatasetImage {
    name: string
    image_url: string
    detection_count: number
    created_at?: string
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
    created_at?: string
    epochs: ModelEpoch[]
  }

  const normalizeEpochMetrics = (run: any): ModelRun => ({
    ...run,
    epochs: Array.isArray(run.epochs)
      ? run.epochs.map((epoch: any) => ({
          epoch: Number(epoch.epoch),
          train_box_loss: Number(epoch.train_box_loss),
          val_box_loss: Number(epoch.val_box_loss),
          precision: Number(epoch.precision),
          recall: Number(epoch.recall),
          map50: Number(epoch.map50),
          map50_95: Number(epoch.map50_95)
        })).filter((epoch: ModelEpoch) => Number.isFinite(epoch.epoch))
      : []
  })

  const readCachedModelRuns = (): ModelRun[] => {
    try {
      const cachedModels = localStorage.getItem('smiley-model-runs')
      const parsedModels: unknown = cachedModels ? JSON.parse(cachedModels) : []
      return Array.isArray(parsedModels)
        ? parsedModels
            .filter((run) =>
              typeof run?.name === 'string' &&
              Array.isArray(run.epochs) &&
              typeof run.available === 'boolean' &&
              (typeof run.best_epoch === 'number' || run.best_epoch === null)
            )
            .map((run) => normalizeEpochMetrics(run))
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
  const isBehindScenes = ref(false)
  const images = ref<InferenceImage[]>([])
  const imagesLimit = 20
  const imagesOffset = ref(0)
  const imagesTotal = ref(0)
  const isLoadingMoreImages = ref(false)
  const imagesHasMore = computed(() => imagesOffset.value < imagesTotal.value)
  const modelRuns = ref<ModelRun[]>(readCachedModelRuns())
  const modelSortOrder = ref<'newest' | 'oldest'>('newest')
  const changeModelSort = (event: Event) => {
    modelSortOrder.value = (event.target as HTMLSelectElement).value as 'newest' | 'oldest'
    void fetchModels(true)
  }
  const modelsLimit = 20
  const modelsOffset = ref(0)
  const modelsTotal = ref(modelRuns.value.length)
  const isLoadingMoreModels = ref(false)
  const modelsHasMore = computed(() => modelsOffset.value < modelsTotal.value)
  const selectedModel = ref(
    readSelectedModel() || modelRuns.value.find((run) => run.available)?.name || ''
  )
  const isModelPickerOpen = ref(false)
  const trendRun = ref<ModelRun | null>(null)
  const isLoadingModels = ref(false)
  const modelsError = ref('')
  const modelsLoaded = ref(false)
  const validationImages = ref<DatasetImage[]>([])
  const trainingImages = ref<DatasetImage[]>([])
  const datasetSortOrder = ref<'newest' | 'oldest'>('newest')
  const changeDatasetSort = (event: Event) => {
    datasetSortOrder.value = (event.target as HTMLSelectElement).value as 'newest' | 'oldest'
    void fetchDatasetImages(activeDatasetSplit.value)
  }
  const isLoadingValidationImages = ref(false)
  const isLoadingTrainingImages = ref(false)
  const validationImagesError = ref('')
  const trainingImagesError = ref('')
  const validationImagesLoaded = ref(false)
  const trainingImagesLoaded = ref(false)
  const datasetImagesLimit = 20
  const validationImagesOffset = ref(0)
  const trainingImagesOffset = ref(0)
  const validationImagesTotal = ref(0)
  const trainingImagesTotal = ref(0)
  const isLoadingMoreValidationImages = ref(false)
  const isLoadingMoreTrainingImages = ref(false)
  const datasetImagesHasMore = computed(() => {
    if (activeDatasetSplit.value === 'training') return trainingImagesOffset.value < trainingImagesTotal.value
    return validationImagesOffset.value < validationImagesTotal.value
  })
  const isLoadingMoreDatasetImages = computed(() =>
    activeDatasetSplit.value === 'training' ? isLoadingMoreTrainingImages.value : isLoadingMoreValidationImages.value
  )
  const activeDatasetSplit = computed(() => activeTab.value === 'training' ? 'training' : 'validation')
  const activeDatasetImages = computed(() =>
    activeDatasetSplit.value === 'training' ? trainingImages.value : validationImages.value
  )
  const sortedActiveDatasetImages = computed(() => [...activeDatasetImages.value].sort((a, b) => {
    const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
    const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
    return datasetSortOrder.value === 'oldest' ? aTime - bTime : bTime - aTime
  }))
  const sortedModelRuns = computed(() => [...modelRuns.value].sort((a, b) => {
    const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
    const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
    return modelSortOrder.value === 'oldest' ? aTime - bTime : bTime - aTime
  }))
  const isLoadingDatasetImages = computed(() =>
    activeDatasetSplit.value === 'training' ? isLoadingTrainingImages.value : isLoadingValidationImages.value
  )
  const datasetImagesError = computed(() =>
    activeDatasetSplit.value === 'training' ? trainingImagesError.value : validationImagesError.value
  )
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, TaskInfo[]>>({})
  const openTaskMenuId = ref('')
  const savingDatasetTaskId = ref('')
  const datasetSaveMessages = ref<Record<string, string>>({})
  const selectedBulkImageIds = ref<string[]>([])
  const bulkSelectionAnchorId = ref<string | null>(null)
  const isStartingBulkTasks = ref(false)
  const bulkTaskMessage = ref('')
  const correctionTaskGuid = ref('')
  const correctionImage = ref<InferenceImage | null>(null)
  const correctionImageDimensions = ref<{ width: number; height: number } | null>(null)
  const correctionBox = ref<BoxCoordinates | null>(null)
  const correctionAnchor = ref<{ x: number; y: number } | null>(null)
  const correctionCursor = ref<{ x: number; y: number } | null>(null)
  const correctionError = ref('')
  const isSavingCorrection = ref(false)
  const isLoadingCorrectionPreview = ref(false)
  const isCorrectionPreviewOpen = ref(false)
  const correctionPreviewUrl = ref('')
  const correctionDatasetSplit = ref<'train' | 'val'>('train')
  const relabelImage = ref<DatasetImage | null>(null)
  const relabelImageName = ref('')
  const relabelSplit = ref<'training' | 'validation'>('training')
  const relabelImageDimensions = ref<{ width: number; height: number } | null>(null)
  const relabelBox = ref<BoxCoordinates | null>(null)
  const relabelAnchor = ref<{ x: number; y: number } | null>(null)
  const relabelCursor = ref<{ x: number; y: number } | null>(null)
  const relabelError = ref('')
  const isSavingRelabel = ref(false)
  const correctionOverlayBox = computed(() => {
    const first = correctionAnchor.value
    const second = correctionCursor.value
    const box = correctionBox.value
    if (box) {
      return {
        x: box.x_min,
        y: box.y_min,
        width: box.x_max - box.x_min,
        height: box.y_max - box.y_min
      }
    }
    if (first && second) {
      return {
        x: Math.min(first.x, second.x),
        y: Math.min(first.y, second.y),
        width: Math.abs(second.x - first.x),
        height: Math.abs(second.y - first.y)
      }
    }
    return null
  })
  const relabelOverlayBox = computed(() => {
    const first = relabelAnchor.value
    const second = relabelCursor.value
    const box = relabelBox.value
    if (box) return { x: box.x_min, y: box.y_min, width: box.x_max - box.x_min, height: box.y_max - box.y_min }
    if (first && second) return { x: Math.min(first.x, second.x), y: Math.min(first.y, second.y), width: Math.abs(second.x - first.x), height: Math.abs(second.y - first.y) }
    return null
  })
  const relabelLabelPreview = computed(() => {
    const box = relabelBox.value
    const dimensions = relabelImageDimensions.value
    if (!box || !dimensions) return 'Click the first corner, then the opposite corner to draw the new box.'
    return `0 ${(((box.x_min + box.x_max) / 2) / dimensions.width).toFixed(6)} ${(((box.y_min + box.y_max) / 2) / dimensions.height).toFixed(6)} ${((box.x_max - box.x_min) / dimensions.width).toFixed(6)} ${((box.y_max - box.y_min) / dimensions.height).toFixed(6)}`
  })

  const correctionLabelPreview = computed(() => {
    const box = correctionBox.value
    const dimensions = correctionImageDimensions.value
    if (!box || !dimensions) {
      return 'Click the top-left corner, then the bottom-right corner of the smiley.'
    }
    const xCenter = ((box.x_min + box.x_max) / 2) / dimensions.width
    const yCenter = ((box.y_min + box.y_max) / 2) / dimensions.height
    const width = (box.x_max - box.x_min) / dimensions.width
    const height = (box.y_max - box.y_min) / dimensions.height
    return `0 ${xCenter.toFixed(6)} ${yCenter.toFixed(6)} ${width.toFixed(6)} ${height.toFixed(6)}`
  })

  // Track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // Upload state variables
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFiles = ref<File[]>([])
  const isUploading = ref(false)
  const uploadMessage = ref('')

  // Fetch existing uploaded images on mount or after automatic actions
  const fetchImages = async (reset = true) => {
    const requestedOffset = reset ? 0 : imagesOffset.value
    if (!reset) isLoadingMoreImages.value = true
    try {
      const response = await fetch(`/images?limit=${imagesLimit}&offset=${requestedOffset}`)
      if (response.ok) {
        const data = await response.json()
        const uploadedImages = Array.isArray(data) ? data : (data.images || [])
        const sortedImages = uploadedImages.sort((a: InferenceImage, b: InferenceImage) => {
          const aTime = a.uploaded_at ? new Date(a.uploaded_at).getTime() : 0
          const bTime = b.uploaded_at ? new Date(b.uploaded_at).getTime() : 0
          return bTime - aTime
        })
        images.value = reset ? sortedImages : [...images.value, ...sortedImages]
        imagesOffset.value = reset ? sortedImages.length : imagesOffset.value + sortedImages.length
        imagesTotal.value = Array.isArray(data) ? images.value.length : (data.total ?? imagesOffset.value)
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    } finally {
      isLoadingMoreImages.value = false
    }
  }

  const fetchModels = async (reset = true) => {
    if (reset) isLoadingModels.value = true
    else isLoadingMoreModels.value = true
    modelsError.value = ''
    const requestedOffset = reset ? 0 : modelsOffset.value

    try {
      const response = await fetch(`/models?limit=${modelsLimit}&offset=${requestedOffset}&order=${modelSortOrder.value}`)
      if (!response.ok) {
        throw new Error(`Models request failed with status ${response.status}`)
      }

      const data = await response.json()
      const runs = (data.runs || [])
        .map((run: ModelRun) => normalizeEpochMetrics(run))
        .map((run: ModelRun) => ({ ...run, epochs: [...run.epochs].sort((a, b) => b.epoch - a.epoch) }))
      modelRuns.value = reset ? runs : [...modelRuns.value, ...runs]
      modelsOffset.value = reset ? runs.length : modelsOffset.value + runs.length
      modelsTotal.value = data.total ?? modelsOffset.value
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
      isLoadingMoreModels.value = false
    }
  }

  const formatMetric = (value: number | null | undefined) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
    return value.toFixed(4)
  }

  const trendMetrics = [
    { key: 'train_box_loss', label: 'Train box loss', color: '#4f7bd9' },
    { key: 'val_box_loss', label: 'Validation box loss', color: '#e08b45' },
    { key: 'precision', label: 'Precision', color: '#5b9c7a' },
    { key: 'recall', label: 'Recall', color: '#9b6bb0' },
    { key: 'map50', label: 'mAP50', color: '#4f9aab' },
    { key: 'map50_95', label: 'mAP50–95', color: '#d15f75' }
  ] as const

  const getTrendEpochs = (run: ModelRun | null) =>
    run ? [...run.epochs].sort((a, b) => a.epoch - b.epoch) : []

  const getMetricChart = (run: ModelRun | null, metricKey: keyof ModelEpoch) => {
    const epochs = getTrendEpochs(run)
    const width = 360
    const height = 170
    const left = 42
    const right = 12
    const top = 12
    const bottom = 28
    const plotWidth = width - left - right
    const plotHeight = height - top - bottom
    const points = epochs
      .map((epoch) => ({ epoch: epoch.epoch, value: epoch[metricKey] }))
      .filter((point): point is { epoch: number; value: number } => typeof point.value === 'number' && Number.isFinite(point.value))

    if (points.length === 0) return { path: '', min: 0, max: 0, points: [], width, height, left, top, plotWidth, plotHeight }

    const values = points.map((point) => point.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const firstEpoch = points[0].epoch
    const lastEpoch = points[points.length - 1].epoch
    const epochRange = lastEpoch - firstEpoch || 1
    const chartPoints = points.map((point) => ({
      x: left + (points.length === 1 ? plotWidth / 2 : ((point.epoch - firstEpoch) / epochRange) * plotWidth),
      y: top + ((max - point.value) / range) * plotHeight,
      label: `${point.epoch}`,
      value: point.value
    }))
    const path = chartPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
    return { path, min, max, points: chartPoints, width, height, left, top, plotWidth, plotHeight }
  }

  const closeTrendModal = () => { trendRun.value = null }

  const getImageSavedSplit = (img: InferenceImage) => {
    if (img.saved_status === 1 || img.saved_split === 'training') return 'training'
    if (img.saved_status === 2 || img.saved_split === 'validation') return 'validation'
    const savedTask = imageDetails.value[img.guid]?.find((task) => task.saved !== 0)
    if (savedTask) return savedTask.saved === 1 ? 'training' : 'validation'
    return null
  }

  const formatDateTime = (dateTime?: string, unavailableLabel = 'Date unavailable') => {
    if (!dateTime) return unavailableLabel
    const date = new Date(dateTime)
    if (Number.isNaN(date.getTime())) return unavailableLabel
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    }).format(date)
  }

  const formatCreatedAt = (createdAt?: string) => formatDateTime(createdAt, 'Created date unavailable')

  const getBestEpoch = (run: ModelRun) => {
    const exact = run.epochs.find((epoch) => epoch.epoch === run.best_epoch)
    if (exact) return exact
    if (run.epochs.length === 0) return null

    return [...run.epochs].sort((a, b) => {
      const aScore = 0.1 * (a.map50 || 0) + 0.9 * (a.map50_95 || 0)
      const bScore = 0.1 * (b.map50 || 0) + 0.9 * (b.map50_95 || 0)
      return bScore - aScore
    })[0]
  }

  const getBestEpochNumber = (run: ModelRun) => getBestEpoch(run)?.epoch ?? run.best_epoch

  const getBestEpochRows = (run: ModelRun) => {
    const epoch = getBestEpoch(run)
    return epoch ? [epoch] : []
  }

  const getSortedEpochRows = (run: ModelRun) =>
    [...run.epochs].sort((a, b) => b.epoch - a.epoch)

  const chooseModel = (modelName: string) => {
    selectedModel.value = modelName
    writeBrowserCache('smiley-selected-model', modelName)
    isModelPickerOpen.value = false
  }

  const openModelPicker = async () => {
    isModelPickerOpen.value = true
    if (!isLoadingModels.value) {
      await fetchModels()
    }
  }

  const fetchDatasetImages = async (split: 'training' | 'validation', refresh = false, append = false) => {
    const loading = split === 'training' ? isLoadingTrainingImages : isLoadingValidationImages
    const loadingMore = split === 'training' ? isLoadingMoreTrainingImages : isLoadingMoreValidationImages
    const error = split === 'training' ? trainingImagesError : validationImagesError
    const loaded = split === 'training' ? trainingImagesLoaded : validationImagesLoaded
    const datasetImages = split === 'training' ? trainingImages : validationImages
    const offset = split === 'training' ? trainingImagesOffset : validationImagesOffset
    const total = split === 'training' ? trainingImagesTotal : validationImagesTotal
    const requestedOffset = append ? offset.value : 0
    loading.value = !append
    loadingMore.value = append
    error.value = ''

    try {
      const query = new URLSearchParams({
        limit: String(datasetImagesLimit),
        offset: String(requestedOffset),
        order: datasetSortOrder.value
      })
      if (refresh) query.set('refresh', 'true')
      const response = await fetch(`/${split}-images?${query.toString()}`)
      if (!response.ok) {
        throw new Error(`${split} images request failed with status ${response.status}`)
      }

      const data = await response.json()
      const page = data.images || []
      datasetImages.value = append ? [...datasetImages.value, ...page] : page
      offset.value = append ? offset.value + page.length : page.length
      total.value = data.total ?? offset.value
      loaded.value = true
    } catch (err) {
      error.value = `Could not load ${split} images. Please try again.`
      console.error(`Failed to fetch ${split} images:`, err)
    } finally {
      loading.value = false
      loadingMore.value = false
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

  const openBehindScenes = async () => {
    isBehindScenes.value = true
    await selectTab('validation')
  }

  const backToHome = () => {
    isBehindScenes.value = false
    activeTab.value = 'home'
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Handle file selection
  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    selectedFiles.value = target.files ? Array.from(target.files) : []
  }

  // Upload one or more images via /upload-images/
  const uploadImage = async () => {
    if (selectedFiles.value.length === 0) {
      uploadMessage.value = 'Please select at least one file first!'
      return
    }

    const formData = new FormData()
    for (const file of selectedFiles.value) {
      formData.append('imgs', file)
    }

    isUploading.value = true
    uploadMessage.value = ''

    try {
      const response = await fetch('/upload-images/', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      const uploadedCount = selectedFiles.value.length
      uploadMessage.value = `${uploadedCount} ${uploadedCount === 1 ? 'image' : 'images'} uploaded successfully!`
      selectedFiles.value = []
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

  // Fetch tasks for a specific image GUID (used for initial expansion and task polling)
  const fetchTasksForImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/images/${imgGuid}/tasks`)
      if (response.ok) {
        const data = await response.json()
        imageDetails.value[imgGuid] = data.tasks || []
        const image = images.value.find((item) => item.guid === imgGuid)
        if (image) {
          image.task_count = imageDetails.value[imgGuid].length
          const savedTask = imageDetails.value[imgGuid].find((task) => task.saved !== 0)
          image.saved_status = savedTask?.saved || 0
          image.saved_split = savedTask
            ? (savedTask.saved === 1 ? 'training' : 'validation')
            : null
        }
      } else if (response.status === 404) {
        imageDetails.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch tasks for image', err)
    }
  }

  const terminalTaskStatuses = new Set(['SUCCESS', 'FAILURE', 'REVOKED'])
  const taskPollingInFlight = new Set<string>()
  let taskPollingInterval: ReturnType<typeof setInterval> | null = null

  // TODO: Replace short polling with FastAPI WebSockets plus Redis/Celery task events when real-time scale requires it.
  const pollActiveTasks = async () => {
    const guidsToPoll = Object.entries(imageDetails.value)
      .filter(([, tasks]) => tasks.some((task) => !terminalTaskStatuses.has(task.task_status.toUpperCase())))
      .map(([guid]) => guid)

    await Promise.all(guidsToPoll.map(async (guid) => {
      if (taskPollingInFlight.has(guid)) return
      taskPollingInFlight.add(guid)
      try {
        await fetchTasksForImage(guid)
      } finally {
        taskPollingInFlight.delete(guid)
      }
    }))
  }

  const openDatasetRelabel = (image: DatasetImage, split: 'training' | 'validation') => {
    relabelImage.value = image
    relabelImageName.value = image.name
    relabelSplit.value = split
    relabelImageDimensions.value = null
    relabelBox.value = null
    relabelAnchor.value = null
    relabelCursor.value = null
    relabelError.value = ''
  }

  const closeDatasetRelabel = (force = false) => {
    if (isSavingRelabel.value && !force) return
    relabelImage.value = null
    relabelImageName.value = ''
    relabelImageDimensions.value = null
    relabelBox.value = null
    relabelAnchor.value = null
    relabelCursor.value = null
    relabelError.value = ''
  }

  const onRelabelImageLoad = (event: Event) => {
    const image = event.currentTarget as HTMLImageElement
    relabelImageDimensions.value = { width: image.naturalWidth, height: image.naturalHeight }
  }

  const selectRelabelPoint = (event: PointerEvent) => {
    const dimensions = relabelImageDimensions.value
    if (!dimensions) return
    const svg = event.currentTarget as SVGSVGElement
    const bounds = svg.getBoundingClientRect()
    const point = {
      x: Math.max(0, Math.min(dimensions.width, ((event.clientX - bounds.left) / bounds.width) * dimensions.width)),
      y: Math.max(0, Math.min(dimensions.height, ((event.clientY - bounds.top) / bounds.height) * dimensions.height))
    }
    if (!relabelAnchor.value) {
      relabelAnchor.value = point
      relabelCursor.value = point
      relabelBox.value = null
      relabelError.value = ''
      return
    }
    const box = {
      x_min: Math.min(relabelAnchor.value.x, point.x),
      y_min: Math.min(relabelAnchor.value.y, point.y),
      x_max: Math.max(relabelAnchor.value.x, point.x),
      y_max: Math.max(relabelAnchor.value.y, point.y)
    }
    relabelAnchor.value = null
    relabelCursor.value = null
    if (box.x_max <= box.x_min || box.y_max <= box.y_min) {
      relabelError.value = 'Select two different corners to create a positive-size box.'
      return
    }
    relabelBox.value = box
  }

  const updateRelabelPoint = (event: PointerEvent) => {
    if (!relabelAnchor.value || !relabelImageDimensions.value) return
    const svg = event.currentTarget as SVGSVGElement
    const bounds = svg.getBoundingClientRect()
    relabelCursor.value = {
      x: Math.max(0, Math.min(relabelImageDimensions.value.width, ((event.clientX - bounds.left) / bounds.width) * relabelImageDimensions.value.width)),
      y: Math.max(0, Math.min(relabelImageDimensions.value.height, ((event.clientY - bounds.top) / bounds.height) * relabelImageDimensions.value.height))
    }
  }

  const saveDatasetRelabel = async () => {
    const image = relabelImage.value
    if (!image) return
    const box = relabelBox.value
    isSavingRelabel.value = true
    relabelError.value = ''
    try {
      const response = await fetch(`/dataset/${relabelSplit.value}/images/${encodeURIComponent(image.name)}/relabel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ corrected_box: box })
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || `Relabel request failed with status ${response.status}`)
      const datasetImages = relabelSplit.value === 'training' ? trainingImages : validationImages
      datasetImages.value = datasetImages.value.map((datasetImage) => {
        if (datasetImage.name !== image.name) return datasetImage
        return {
          ...datasetImage,
          image_url: typeof result.image_url === 'string' ? result.image_url : datasetImage.image_url,
          detection_count: typeof result.detection_count === 'number' ? result.detection_count : datasetImage.detection_count
        }
      })
      closeDatasetRelabel(true)
    } catch (err) {
      relabelError.value = err instanceof Error ? err.message : 'Could not relabel this dataset image.'
    } finally {
      isSavingRelabel.value = false
    }
  }

  const openCorrectionModal = (task: TaskInfo, image: InferenceImage) => {
    if (correctionPreviewUrl.value) URL.revokeObjectURL(correctionPreviewUrl.value)
    correctionPreviewUrl.value = ''
    isCorrectionPreviewOpen.value = false
    correctionTaskGuid.value = task.guid
    correctionImage.value = image
    correctionImageDimensions.value = null
    correctionBox.value = null
    correctionAnchor.value = null
    correctionCursor.value = null
    correctionError.value = ''
    correctionDatasetSplit.value = 'train'
    openTaskMenuId.value = ''
  }

  const closeCorrectionModal = (force = false) => {
    if (isSavingCorrection.value && !force) return
    correctionTaskGuid.value = ''
    correctionImage.value = null
    correctionImageDimensions.value = null
    correctionBox.value = null
    correctionAnchor.value = null
    correctionCursor.value = null
    correctionError.value = ''
    if (correctionPreviewUrl.value) {
      URL.revokeObjectURL(correctionPreviewUrl.value)
      correctionPreviewUrl.value = ''
    }
    isCorrectionPreviewOpen.value = false
  }

  const onCorrectionImageLoad = (event: Event) => {
    const image = event.currentTarget as HTMLImageElement
    correctionImageDimensions.value = {
      width: image.naturalWidth,
      height: image.naturalHeight
    }
  }

  const selectCorrectionPoint = (event: PointerEvent) => {
    const dimensions = correctionImageDimensions.value
    if (!dimensions) return

    const svg = event.currentTarget as SVGSVGElement
    const bounds = svg.getBoundingClientRect()
    const point = {
      x: Math.max(0, Math.min(dimensions.width, ((event.clientX - bounds.left) / bounds.width) * dimensions.width)),
      y: Math.max(0, Math.min(dimensions.height, ((event.clientY - bounds.top) / bounds.height) * dimensions.height))
    }

    if (!correctionAnchor.value) {
      correctionAnchor.value = point
      correctionCursor.value = point
      correctionBox.value = null
      correctionError.value = ''
      return
    }

    const box = {
      x_min: Math.min(correctionAnchor.value.x, point.x),
      y_min: Math.min(correctionAnchor.value.y, point.y),
      x_max: Math.max(correctionAnchor.value.x, point.x),
      y_max: Math.max(correctionAnchor.value.y, point.y)
    }
    correctionAnchor.value = null
    correctionCursor.value = null
    if (box.x_max <= box.x_min || box.y_max <= box.y_min) {
      correctionError.value = 'The box must have positive width and height. Select two different corners.'
      return
    }
    correctionBox.value = box
  }

  const updateCorrectionPreviewPoint = (event: PointerEvent) => {
    const dimensions = correctionImageDimensions.value
    if (!dimensions || !correctionAnchor.value) return

    const svg = event.currentTarget as SVGSVGElement
    const bounds = svg.getBoundingClientRect()
    correctionCursor.value = {
      x: Math.max(0, Math.min(dimensions.width, ((event.clientX - bounds.left) / bounds.width) * dimensions.width)),
      y: Math.max(0, Math.min(dimensions.height, ((event.clientY - bounds.top) / bounds.height) * dimensions.height))
    }
  }

  const openCorrectionConfirmation = async () => {
    const box = correctionBox.value
    const taskGuid = correctionTaskGuid.value
    if (!box || !taskGuid) return

    isLoadingCorrectionPreview.value = true
    correctionError.value = ''
    try {
      const response = await fetch(`/tasks/${taskGuid}/corrected-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(box)
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `Preview request failed with status ${response.status}`)
      }

      if (correctionPreviewUrl.value) URL.revokeObjectURL(correctionPreviewUrl.value)
      correctionPreviewUrl.value = URL.createObjectURL(await response.blob())
      isCorrectionPreviewOpen.value = true
    } catch (err) {
      correctionError.value = err instanceof Error ? err.message : 'Could not render the corrected-box preview.'
      console.error('Failed to render corrected-box preview:', err)
    } finally {
      isLoadingCorrectionPreview.value = false
    }
  }

  const closeCorrectionConfirmation = () => {
    if (isSavingCorrection.value) return
    isCorrectionPreviewOpen.value = false
    if (correctionPreviewUrl.value) {
      URL.revokeObjectURL(correctionPreviewUrl.value)
      correctionPreviewUrl.value = ''
    }
  }

  const saveCorrectedDatasetData = async () => {
    const box = correctionBox.value
    const taskGuid = correctionTaskGuid.value
    const split = correctionDatasetSplit.value
    if (!box || !taskGuid) return

    const splitLabel = split === 'train' ? 'training' : 'validation'
    isSavingCorrection.value = true
    correctionError.value = ''
    datasetSaveMessages.value[taskGuid] = ''
    try {
      const response = await fetch(`/tasks/${taskGuid}/add-to-dataset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ split, corrected_box: box })
      })
      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.detail || `Server returned status ${response.status}`)
      }

      for (const taskList of Object.values(imageDetails.value)) {
        const task = taskList.find((item) => item.guid === taskGuid)
        if (task) task.saved = result.saved
      }
      datasetSaveMessages.value[taskGuid] = `Saved ${result.image} to ${splitLabel} data with your corrected box.`
      if (split === 'train') trainingImagesLoaded.value = false
      else validationImagesLoaded.value = false
      closeCorrectionConfirmation()
      closeCorrectionModal(true)
    } catch (err) {
      correctionError.value = err instanceof Error ? err.message : `Could not save corrected ${splitLabel} data.`
      console.error(`Failed to save corrected ${splitLabel} data:`, err)
    } finally {
      isSavingCorrection.value = false
    }
  }

  const saveNoDetections = async () => {
    const taskGuid = correctionTaskGuid.value
    const split = correctionDatasetSplit.value
    if (!taskGuid) return
    const splitLabel = split === 'train' ? 'training' : 'validation'
    const accepted = window.confirm(`Accept no detections? This image will be saved as ${splitLabel} data with no bounding boxes.`)
    if (!accepted) return

    isSavingCorrection.value = true
    correctionError.value = ''
    datasetSaveMessages.value[taskGuid] = ''
    try {
      const response = await fetch(`/tasks/${taskGuid}/add-to-dataset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ split, accept_no_detections: true })
      })
      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.detail || `Server returned status ${response.status}`)
      }

      for (const taskList of Object.values(imageDetails.value)) {
        const task = taskList.find((item) => item.guid === taskGuid)
        if (task) task.saved = result.saved
      }
      datasetSaveMessages.value[taskGuid] = `Saved ${result.image} to ${splitLabel} data with no detections.`
      if (split === 'train') trainingImagesLoaded.value = false
      else validationImagesLoaded.value = false
      closeCorrectionModal(true)
    } catch (err) {
      correctionError.value = err instanceof Error ? err.message : `Could not save no-detections ${splitLabel} data.`
    } finally {
      isSavingCorrection.value = false
    }
  }

  const addTaskToDataset = async (taskGuid: string, split: 'train' | 'val') => {
    const splitLabel = split === 'train' ? 'training' : 'validation'
    const confirmed = window.confirm(
      `Are you sure? The prediction and the image will be saved as ${splitLabel} data without any corrections.`
    )
    if (!confirmed) {
      openTaskMenuId.value = ''
      return
    }

    savingDatasetTaskId.value = taskGuid
    datasetSaveMessages.value[taskGuid] = ''
    try {
      const response = await fetch(`/tasks/${taskGuid}/add-to-dataset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ split })
      })
      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.detail || `Server returned status ${response.status}`)
      }

      datasetSaveMessages.value[taskGuid] = `Saved ${result.image} to ${splitLabel} data.`
      for (const tasks of Object.values(imageDetails.value)) {
        const task = tasks.find((item) => item.guid === taskGuid)
        if (task) {
          task.saved = result.saved
        }
      }
      if (split === 'train') {
        trainingImagesLoaded.value = false
      } else {
        validationImagesLoaded.value = false
      }
      openTaskMenuId.value = ''
    } catch (err) {
      datasetSaveMessages.value[taskGuid] = err instanceof Error ? err.message : 'Could not save task to dataset.'
      console.error('Failed to add task to dataset:', err)
    } finally {
      savingDatasetTaskId.value = ''
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

  const toggleBulkImageSelection = (imageGuid: string, event?: Event) => {
    const checkboxEvent = event as MouseEvent | undefined
    const checkbox = event?.target instanceof HTMLInputElement ? event.target : null
    const isChecked = checkbox?.checked ?? !selectedBulkImageIds.value.includes(imageGuid)

    if (checkboxEvent?.shiftKey && bulkSelectionAnchorId.value) {
      const anchorIndex = images.value.findIndex((img) => img.guid === bulkSelectionAnchorId.value)
      const targetIndex = images.value.findIndex((img) => img.guid === imageGuid)
      if (anchorIndex >= 0 && targetIndex >= 0) {
        const start = Math.min(anchorIndex, targetIndex)
        const end = Math.max(anchorIndex, targetIndex)
        const rangeIds = images.value.slice(start, end + 1).map((img) => img.guid)
        if (isChecked) {
          selectedBulkImageIds.value = [...new Set([...selectedBulkImageIds.value, ...rangeIds])]
        } else {
          selectedBulkImageIds.value = selectedBulkImageIds.value.filter((guid) => !rangeIds.includes(guid))
        }
        return
      }
    }

    if (isChecked) {
      selectedBulkImageIds.value = [...new Set([...selectedBulkImageIds.value, imageGuid])]
    } else {
      selectedBulkImageIds.value = selectedBulkImageIds.value.filter((guid) => guid !== imageGuid)
    }
    bulkSelectionAnchorId.value = imageGuid
  }

  const startBulkTasks = async (imageGuids: string[]) => {
    if (!selectedModel.value) {
      isModelPickerOpen.value = true
      return
    }
    if (imageGuids.length === 0) {
      bulkTaskMessage.value = 'Select at least one image to start tasks.'
      return
    }

    isStartingBulkTasks.value = true
    bulkTaskMessage.value = ''
    try {
      const response = await fetch('/process-images/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: selectedModel.value, image_guids: imageGuids })
      })
      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.detail || `Bulk task request failed with status ${response.status}`)
      }

      bulkTaskMessage.value = result.failed_count > 0
        ? `Started ${result.created_count} tasks; ${result.failed_count} failed.`
        : `Started tasks for ${result.created_count} ${result.created_count === 1 ? 'image' : 'images'}.`
      selectedBulkImageIds.value = []
      bulkSelectionAnchorId.value = null
      await Promise.all(imageGuids.map((guid) => fetchTasksForImage(guid)))
    } catch (err) {
      bulkTaskMessage.value = err instanceof Error ? err.message : 'Could not start bulk tasks.'
    } finally {
      isStartingBulkTasks.value = false
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
    taskPollingInterval = setInterval(pollActiveTasks, 2000)
  })

  onUnmounted(() => {
    if (taskPollingInterval !== null) {
      clearInterval(taskPollingInterval)
      taskPollingInterval = null
    }
  })
</script>

<template>
  <main class="dashboard">
    <div class="dashboard__shell">
      <div class="page-topbar" aria-label="Page navigation">
        <button
          v-if="isBehindScenes"
          class="page-link page-link--back"
          type="button"
          @click="backToHome"
        >
          <span aria-hidden="true">←</span>
          <span>Back to Home</span>
        </button>
        <span v-else aria-hidden="true"></span>
        <button
          v-if="!isBehindScenes"
          class="page-link page-link--forward"
          type="button"
          @click="openBehindScenes"
        >
          <span>Behind the Scenes</span>
          <span aria-hidden="true">→</span>
        </button>
      </div>

      <header class="page-header">
        <div class="brand-mark" aria-hidden="true">S</div>
        <div class="page-header__copy">
          <p class="eyebrow">IMAGE ANALYSIS</p>
          <h1>Smiley Detection</h1>
          <p class="page-header__subtitle">Upload images, run detection, and review your results.</p>
        </div>
      </header>

      <nav v-if="isBehindScenes" class="tab-nav" aria-label="Behind the scenes navigation">
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

      <div v-if="activeTab === 'home'">
      <section class="panel upload-panel" aria-labelledby="upload-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">GET STARTED</p>
            <h2 id="upload-heading">Add an image</h2>
            <p class="section-description">Choose one or more JPG or PNG images to run smiley detection.</p>
          </div>
          <span class="upload-icon" aria-hidden="true">↑</span>
        </div>

        <div class="upload-controls">
          <label class="file-picker" :class="{ 'file-picker--selected': selectedFiles.length > 0 }">
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg, image/jpg, image/png"
              multiple
              @change="handleFileChange"
            />
            <span class="file-picker__icon" aria-hidden="true">＋</span>
            <span class="file-picker__text">
              <strong>{{ selectedFiles.length === 1 ? selectedFiles[0].name : selectedFiles.length > 1 ? `${selectedFiles.length} images selected` : 'Choose images' }}</strong>
              <small>{{ selectedFiles.length > 0 ? 'Ready to upload' : 'JPG or PNG, select one or more files from your device' }}</small>
            </span>
            <span class="file-picker__action">Browse</span>
          </label>
          <button
            class="button button--primary upload-button"
            type="button"
            :disabled="isUploading || selectedFiles.length === 0"
            @click="uploadImage"
          >
            <span v-if="isUploading" class="button-spinner" aria-hidden="true"></span>
            {{ isUploading ? 'Uploading' : selectedFiles.length > 1 ? 'Upload images' : 'Upload image' }}
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
          <div class="library-heading__actions">
            <button
              v-if="!isBehindScenes"
              class="selected-model-link"
              type="button"
              :title="`Change selected model. Current model: ${selectedModel || 'No model selected'}`"
              @click="openModelPicker"
            >
              <span class="selected-model-link__name">{{ selectedModel || 'No model selected' }}</span>
              <span class="selected-model-link__pencil" aria-hidden="true">✎</span>
            </button>
            <button
              class="button button--primary"
              type="button"
              :disabled="isStartingBulkTasks || selectedBulkImageIds.length === 0"
              @click="startBulkTasks(selectedBulkImageIds)"
            >
              <span v-if="isStartingBulkTasks" class="button-spinner" aria-hidden="true"></span>
              {{ isStartingBulkTasks ? 'Starting tasks…' : `Start tasks (${selectedBulkImageIds.length})` }}
            </button>
          </div>
        </div>

        <p
          v-if="bulkTaskMessage"
          class="feedback-message"
          :class="bulkTaskMessage.startsWith('Started') ? 'feedback-message--success' : 'feedback-message--error'"
          role="status"
        >
          {{ bulkTaskMessage }}
        </p>

        <div v-if="images.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>Your library is empty</h3>
          <p>Upload an image above to get started. Your images and detection tasks will appear here.</p>
        </div>

        <div v-else class="image-list">
          <article
            v-for="img in images"
            :key="img.guid"
            class="image-card"
            :class="{ 'image-card--menu-open': openTaskMenuId && imageDetails[img.guid]?.some((task) => task.guid === openTaskMenuId) }"
          >
            <div class="image-card__summary">
              <label class="bulk-image-select" :title="`Select ${img.name}`">
                <input
                  type="checkbox"
                  :checked="selectedBulkImageIds.includes(img.guid)"
                  @click="toggleBulkImageSelection(img.guid, $event)"
                />
              </label>
              <button
                class="image-card__toggle"
                type="button"
                :aria-expanded="!!expandedImages[img.guid]"
                @click="toggleExpand(img)"
              >
                <img class="image-card__thumbnail" :src="`/${img.filepath}`" :alt="`Thumbnail of ${img.name}`" loading="lazy" decoding="async" />
                <span class="image-card__details">
                  <strong class="image-card__name">{{ img.name }}</strong>
                  <span class="image-card__path">{{ img.filepath }}</span>
                  <time v-if="img.uploaded_at" :datetime="img.uploaded_at" class="image-card__uploaded">
                    Uploaded {{ formatDateTime(img.uploaded_at) }}
                  </time>
                  <span
                    v-if="getImageSavedSplit(img)"
                    class="parent-saved-badge"
                    :class="`parent-saved-badge--${getImageSavedSplit(img)}`"
                  >
                    Saved to {{ getImageSavedSplit(img) === 'training' ? 'Training' : 'Validation' }}
                  </span>
                  <span v-else class="parent-unsaved-label">Not saved to a dataset</span>
                </span>
                <span class="image-card__chevron" :class="{ 'image-card__chevron--expanded': expandedImages[img.guid] }" aria-hidden="true">
                  ⌄
                </span>
              </button>
              <span class="image-card__task-count">
                {{ img.task_count }}
                {{ img.task_count === 1 ? 'task' : 'tasks' }}
              </span>
            </div>

            <div v-if="expandedImages[img.guid]" class="image-card__content">
              <div class="image-overview">
                <div class="preview-frame">
                  <img
                    class="preview-frame__image"
                    :src="activeTaskId[img.guid] ? `/tasks/${activeTaskId[img.guid]}/rendered-image` : `/${img.filepath}`"
                    :alt="activeTaskId[img.guid] ? `Detection result for ${img.name}` : `Preview of ${img.name}`"
                    loading="lazy"
                    decoding="async"
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
                </div>

                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="task-empty">
                  No tasks yet. Run detection to create the first task.
                </div>
                <ul v-else class="task-list">
                  <li v-for="task in imageDetails[img.guid]" :key="task.guid" class="task-list__item">
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
                        <span class="saved-badge" :class="`saved-badge--${task.saved}`">
                          {{ task.saved === 1 ? 'Saved to Training' : task.saved === 2 ? 'Saved to Validation' : 'Unsaved' }}
                        </span>
                        <span class="detection-count">
                          <strong>{{ task.detection_count }}</strong>
                          {{ task.detection_count === 1 ? 'detection' : 'detections' }}
                        </span>
                      </span>
                    </button>
                    <div class="task-menu">
                      <button
                        class="task-menu__trigger"
                        type="button"
                        :aria-label="`Actions for task ${task.guid}`"
                        :aria-expanded="openTaskMenuId === task.guid"
                        :disabled="savingDatasetTaskId === task.guid"
                        @click.stop="openTaskMenuId = openTaskMenuId === task.guid ? '' : task.guid"
                      >
                        <span aria-hidden="true">⋮</span>
                      </button>
                      <div v-if="openTaskMenuId === task.guid" class="task-menu__popover">
                        <button
                          type="button"
                          :disabled="task.task_status !== 'SUCCESS' || task.saved !== 0 || !!getImageSavedSplit(img) || savingDatasetTaskId === task.guid"
                          @click="addTaskToDataset(task.guid, 'train')"
                        >
                          Add as training data
                        </button>
                        <button
                          type="button"
                          :disabled="task.task_status !== 'SUCCESS' || task.saved !== 0 || !!getImageSavedSplit(img) || savingDatasetTaskId === task.guid"
                          @click="addTaskToDataset(task.guid, 'val')"
                        >
                          Add as validation data
                        </button>
                        <button
                          type="button"
                          :disabled="task.task_status !== 'SUCCESS' || task.saved !== 0 || !!getImageSavedSplit(img) || savingDatasetTaskId === task.guid"
                          @click="openCorrectionModal(task, img)"
                        >
                          Correct and add as training/validation data
                        </button>
                      </div>
                    </div>
                    <p
                      v-if="datasetSaveMessages[task.guid]"
                      class="task-menu__message"
                      :class="{ 'task-menu__message--error': !datasetSaveMessages[task.guid].startsWith('Saved ') }"
                      role="status"
                    >
                      {{ datasetSaveMessages[task.guid] }}
                    </p>
                  </li>
                </ul>
              </div>
            </div>
          </article>
        </div>
        <button
          v-if="imagesHasMore"
          class="button button--secondary lazy-load-button"
          type="button"
          :disabled="isLoadingMoreImages"
          @click="fetchImages(false)"
        >
          {{ isLoadingMoreImages ? 'Loading images…' : 'Load more images' }}
        </button>
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
          <label class="sort-control">
            <span>Order</span>
            <select v-model="datasetSortOrder" aria-label="Order dataset images" @change="changeDatasetSort">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
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
          <article v-for="img in sortedActiveDatasetImages" :key="img.name" class="validation-card">
            <div class="validation-card__image">
              <img
                :src="img.image_url"
                :alt="`Ground-truth bounding boxes for ${img.name}`"
                loading="lazy"
                decoding="async"
              />
            </div>
            <div class="validation-card__details">
              <div class="validation-card__identity">
                <h3>{{ img.name }}</h3>
                <time v-if="img.created_at" :datetime="img.created_at" class="created-on">
                  Created {{ formatCreatedAt(img.created_at) }}
                </time>
              </div>
              <span class="detection-count">
                <strong>{{ img.detection_count }}</strong>
                {{ img.detection_count === 1 ? 'detection' : 'detections' }}
              </span>
              <button
                class="button button--secondary validation-card__relabel"
                type="button"
                @click="openDatasetRelabel(img, activeDatasetSplit)"
              >
                Relabel box
              </button>
            </div>
          </article>
        </div>
        <button
          v-if="datasetImagesHasMore"
          class="button button--secondary lazy-load-button"
          type="button"
          :disabled="isLoadingMoreDatasetImages"
          @click="fetchDatasetImages(activeDatasetSplit, false, true)"
        >
          {{ isLoadingMoreDatasetImages ? 'Loading images…' : 'Load more images' }}
        </button>
      </section>

      <section v-else class="models-section" aria-labelledby="models-heading">
        <div class="library-heading">
          <div>
            <p class="eyebrow">TRAINING HISTORY</p>
            <h2 id="models-heading">Model runs</h2>
            <p class="section-description">Training and validation metrics for each saved run.</p>
          </div>
          <label class="sort-control">
            <span>Order</span>
            <select v-model="modelSortOrder" aria-label="Order model runs" @change="changeModelSort">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>

        <div v-if="isLoadingModels" class="validation-loading" role="status" aria-live="polite">
          <span class="validation-spinner" aria-hidden="true"></span>
          <span>Loading model runs…</span>
        </div>

        <div v-else-if="modelsError" class="validation-error" role="alert">
          <p>{{ modelsError }}</p>
          <button class="button button--secondary" type="button" @click="() => fetchModels(true)">
            Try again
          </button>
        </div>

        <div v-else-if="modelRuns.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>No model runs found</h3>
          <p>Saved training runs with results.csv files will appear here.</p>
        </div>

        <div v-else class="model-run-list">
          <article v-for="run in sortedModelRuns" :key="run.name" class="model-run">
            <header class="model-run__header">
              <div class="model-run__title-group">
                <div class="model-run__title">
                  <h3>{{ run.name }}</h3>
                  <span
                    v-if="run.note"
                    class="model-note-icon"
                    tabindex="0"
                    role="img"
                    aria-label="Model note"
                    :data-tooltip="run.note"
                  >
                    📝
                  </span>
                  <span v-if="getBestEpochNumber(run) !== null" class="model-run__best">
                    Best - Epoch {{ getBestEpochNumber(run) }}
                  </span>
                </div>
                <time v-if="run.created_at" :datetime="run.created_at" class="created-on">
                  Created {{ formatCreatedAt(run.created_at) }}
                </time>
              </div>
              <div class="model-run__actions">
                <button
                  v-if="run.epochs.length"
                  class="button button--secondary model-run__trends-button"
                  type="button"
                  @click="trendRun = run"
                >
                  View Trends
                </button>
                <span class="model-run__epoch-count">{{ run.epochs.length }} epochs</span>
              </div>
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
                    v-for="epoch in getSortedEpochRows(run)"
                    :key="epoch.epoch"
                    :class="{ 'model-run__best-row': epoch.epoch === getBestEpochNumber(run) }"
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
        <button
          v-if="modelsHasMore"
          class="button button--secondary lazy-load-button"
          type="button"
          :disabled="isLoadingMoreModels"
          @click="() => fetchModels(false)"
        >
          {{ isLoadingMoreModels ? 'Loading models…' : 'Load more models' }}
        </button>
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
          <article v-for="run in sortedModelRuns" :key="run.name" class="model-picker__run">
            <div class="model-picker__run-heading">
              <div class="model-run__title">
                <h3>{{ run.name }}</h3>
                <span
                  v-if="run.note"
                  class="model-note-icon"
                  tabindex="0"
                  role="img"
                  aria-label="Model note"
                  :data-tooltip="run.note"
                >
                  📝
                </span>
                <span v-if="getBestEpochNumber(run) !== null" class="model-run__best">
                  Best - Epoch {{ getBestEpochNumber(run) }}
                </span>
                <p v-if="getBestEpoch(run)" class="model-picker__best-values">
                  Train {{ formatMetric(getBestEpoch(run)?.train_box_loss) }} ·
                  Val {{ formatMetric(getBestEpoch(run)?.val_box_loss) }} ·
                  Precision {{ formatMetric(getBestEpoch(run)?.precision) }} ·
                  Recall {{ formatMetric(getBestEpoch(run)?.recall) }} ·
                  mAP50 {{ formatMetric(getBestEpoch(run)?.map50) }} ·
                  mAP50–95 {{ formatMetric(getBestEpoch(run)?.map50_95) }}
                </p>
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

    <div
      v-if="trendRun"
      class="trend-modal-backdrop"
      role="presentation"
      @click.self="closeTrendModal"
    >
      <section class="trend-modal" role="dialog" aria-modal="true" aria-labelledby="trend-modal-heading">
        <header class="trend-modal__header">
          <div>
            <p class="eyebrow">TRAINING TRENDS</p>
            <h2 id="trend-modal-heading">{{ trendRun.name }}</h2>
            <p class="section-description">Metrics across all recorded epochs.</p>
          </div>
          <button class="model-picker__close" type="button" aria-label="Close trends" @click="closeTrendModal">×</button>
        </header>
        <div class="trend-modal__body">
          <article v-for="metric in trendMetrics" :key="metric.key" class="trend-chart">
            <header class="trend-chart__header">
              <h3>{{ metric.label }}</h3>
              <span v-if="getMetricChart(trendRun, metric.key).points.length">
                {{ formatMetric(getMetricChart(trendRun, metric.key).min) }}–{{ formatMetric(getMetricChart(trendRun, metric.key).max) }}
              </span>
            </header>
            <svg
              class="trend-chart__svg"
              :viewBox="`0 0 ${getMetricChart(trendRun, metric.key).width} ${getMetricChart(trendRun, metric.key).height}`"
              role="img"
              :aria-label="`${metric.label} by epoch`"
            >
              <line
                :x1="getMetricChart(trendRun, metric.key).left"
                :x2="getMetricChart(trendRun, metric.key).width - 12"
                :y1="getMetricChart(trendRun, metric.key).height - 28"
                :y2="getMetricChart(trendRun, metric.key).height - 28"
                class="trend-chart__axis"
              />
              <polyline
                v-if="getMetricChart(trendRun, metric.key).path"
                :points="getMetricChart(trendRun, metric.key).points.map((point) => `${point.x},${point.y}`).join(' ')"
                fill="none"
                :stroke="metric.color"
                stroke-width="3"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <circle
                v-for="point in getMetricChart(trendRun, metric.key).points"
                :key="point.label"
                :cx="point.x"
                :cy="point.y"
                r="3.5"
                :fill="metric.color"
              />
              <text
                v-for="point in getMetricChart(trendRun, metric.key).points"
                :key="`label-${point.label}`"
                :x="point.x"
                :y="getMetricChart(trendRun, metric.key).height - 10"
                class="trend-chart__label"
                text-anchor="middle"
              >{{ point.label }}</text>
            </svg>
          </article>
        </div>
      </section>
    </div>

    <div
      v-if="relabelImage"
      class="correction-modal-backdrop"
      role="presentation"
      @click.self="closeDatasetRelabel()"
    >
      <section
        class="correction-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="relabel-modal-heading"
      >
        <header class="correction-modal__header">
          <div>
            <p class="eyebrow">RELABEL DATASET IMAGE</p>
            <h2 id="relabel-modal-heading">Replace the bounding box</h2>
            <p class="section-description">
              Existing labels are shown in red. Click two corners to draw the replacement label in blue.
            </p>
          </div>
          <button
            class="model-picker__close"
            type="button"
            aria-label="Close relabel dialog"
            :disabled="isSavingRelabel"
            @click="closeDatasetRelabel()"
          >
            ×
          </button>
        </header>

        <div class="correction-modal__body">
          <div
            class="correction-canvas"
            :style="relabelImageDimensions
              ? { aspectRatio: `${relabelImageDimensions.width} / ${relabelImageDimensions.height}` }
              : undefined"
          >
            <img
              :src="relabelImage.image_url"
              :alt="`Relabel ${relabelImage.name}`"
              @load="onRelabelImageLoad"
              @error="relabelError = 'Could not load this dataset image.'"
            />
            <svg
              v-if="relabelImageDimensions"
              class="correction-canvas__overlay"
              :viewBox="`0 0 ${relabelImageDimensions.width} ${relabelImageDimensions.height}`"
              preserveAspectRatio="none"
              role="presentation"
              @pointerup="selectRelabelPoint"
              @pointermove="updateRelabelPoint"
            >
              <rect
                v-if="relabelOverlayBox && relabelOverlayBox.width > 0 && relabelOverlayBox.height > 0"
                :x="relabelOverlayBox.x"
                :y="relabelOverlayBox.y"
                :width="relabelOverlayBox.width"
                :height="relabelOverlayBox.height"
                class="correction-canvas__box"
              />
            </svg>
          </div>
          <div class="correction-label">
            <strong>{{ relabelSplit === 'training' ? 'YOLO training' : 'YOLO validation' }} label (class x_center y_center width height)</strong>
            <code>{{ relabelLabelPreview }}</code>
          </div>
          <p v-if="relabelError" class="correction-modal__error" role="alert">{{ relabelError }}</p>
        </div>
        <footer class="correction-modal__footer">
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingRelabel"
            @click="closeDatasetRelabel()"
          >
            Cancel
          </button>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingRelabel"
            @click="relabelBox = null; relabelAnchor = null; relabelCursor = null; relabelError = ''"
          >
            Redraw box
          </button>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingRelabel"
            @click="relabelBox = null; relabelAnchor = null; relabelCursor = null; saveDatasetRelabel()"
          >
            Accept no detections
          </button>
          <button
            class="button button--primary"
            type="button"
            :disabled="!relabelBox || isSavingRelabel"
            @click="saveDatasetRelabel()"
          >
            {{ isSavingRelabel ? 'Saving…' : 'Save relabel' }}
          </button>
        </footer>
      </section>
    </div>

    <div
      v-if="correctionTaskGuid && correctionImage"
      class="correction-modal-backdrop"
      role="presentation"
      @click.self="closeCorrectionModal()"
    >
      <section
        class="correction-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="correction-modal-heading"
      >
        <header class="correction-modal__header">
          <div>
            <p class="eyebrow">CORRECT LABEL</p>
            <h2 id="correction-modal-heading">Draw a smiley bounding box</h2>
            <p class="section-description">
              Click the top-left corner and then the bottom-right corner of the smiley. The image is saved to training data with this label.
            </p>
          </div>
          <button
            class="model-picker__close"
            type="button"
            aria-label="Close correction dialog"
            :disabled="isSavingCorrection"
            @click="closeCorrectionModal()"
          >
            ×
          </button>
        </header>

        <div class="correction-modal__body">
          <div
            class="correction-canvas"
            :style="correctionImageDimensions
              ? { aspectRatio: `${correctionImageDimensions.width} / ${correctionImageDimensions.height}` }
              : undefined"
          >
            <img
              :src="`/tasks/${correctionTaskGuid}/rendered-image`"
              :alt="`Draw a corrected box around the smiley in ${correctionImage.name}`"
              @load="onCorrectionImageLoad"
              @error="correctionError = 'Could not load the original image.'"
            />
            <svg
              v-if="correctionImageDimensions"
              class="correction-canvas__overlay"
              :viewBox="`0 0 ${correctionImageDimensions.width} ${correctionImageDimensions.height}`"
              preserveAspectRatio="none"
              role="presentation"
              @pointerup="selectCorrectionPoint"
              @pointermove="updateCorrectionPreviewPoint"
            >
              <rect
                v-if="correctionOverlayBox && correctionOverlayBox.width > 0 && correctionOverlayBox.height > 0"
                :x="correctionOverlayBox.x"
                :y="correctionOverlayBox.y"
                :width="correctionOverlayBox.width"
                :height="correctionOverlayBox.height"
                class="correction-canvas__box"
              />
            </svg>
          </div>
          <div class="correction-label">
            <strong>{{ correctionDatasetSplit === 'train' ? 'YOLO training' : 'YOLO validation' }} label (class x_center y_center width height)</strong>
            <code>{{ correctionLabelPreview }}</code>
          </div>
          <p v-if="correctionError" class="correction-modal__error" role="alert">{{ correctionError }}</p>
        </div>
        <footer class="correction-modal__footer">          <label class="correction-dataset-picker">
            <span>Save to</span>
            <select v-model="correctionDatasetSplit" aria-label="Dataset split">
              <option value="train">Training</option>
              <option value="val">Validation</option>
            </select>
          </label>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingCorrection"
            @click="closeCorrectionModal()"
          >
            Cancel
          </button>
          <button
            class="button button--secondary"
            type="button"
            :disabled="!correctionBox || isSavingCorrection"
            @click="correctionBox = null; correctionAnchor = null; correctionCursor = null; correctionError = ''"
          >
            Redraw box
          </button>
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingCorrection"
            @click="saveNoDetections"
          >
            Accept no detections
          </button>
          <button
            class="button button--primary"
            type="button"
            :disabled="!correctionBox || isSavingCorrection || isLoadingCorrectionPreview"
            @click="openCorrectionConfirmation"
          >
            <span v-if="isLoadingCorrectionPreview" class="button-spinner" aria-hidden="true"></span>
            {{ isLoadingCorrectionPreview ? 'Preparing preview…' : 'Review and save' }}
          </button>
        </footer>
      </section>
    </div>

    <div
      v-if="isCorrectionPreviewOpen && correctionPreviewUrl"
      class="correction-confirm-backdrop"
      role="presentation"
      @click.self="closeCorrectionConfirmation"
    >
      <section
        class="correction-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="correction-confirm-heading"
      >
        <header class="correction-modal__header">
          <div>
            <p class="eyebrow">CONFIRM {{ correctionDatasetSplit === 'train' ? 'TRAINING' : 'VALIDATION' }} DATA</p>
            <h2 id="correction-confirm-heading">Review the corrected image</h2>
            <p class="section-description">
              Confirm that the blue corrective box correctly surrounds the smiley before saving this image and label to {{ correctionDatasetSplit === 'train' ? 'training' : 'validation' }} data. Existing red prediction boxes may remain visible.
            </p>
          </div>
        </header>
        <div class="correction-confirm__body">
          <img
            class="correction-confirm__image"
            :src="correctionPreviewUrl"
            :alt="`Backend-rendered bounding box preview for ${correctionImage?.name || 'the image'}`"
          />
          <div class="correction-label">
            <strong>{{ correctionDatasetSplit === 'train' ? 'YOLO training' : 'YOLO validation' }} label (class x_center y_center width height)</strong>
            <code>{{ correctionLabelPreview }}</code>
          </div>
          <p v-if="correctionError" class="correction-modal__error" role="alert">{{ correctionError }}</p>
        </div>
        <footer class="correction-modal__footer">
          <button
            class="button button--secondary"
            type="button"
            :disabled="isSavingCorrection"
            @click="closeCorrectionConfirmation"
          >
            Cancel
          </button>
          <button
            class="button button--primary"
            type="button"
            :disabled="isSavingCorrection"
            @click="saveCorrectedDatasetData"
          >
            {{ isSavingCorrection ? 'Saving…' : 'Confirm and save' }}
          </button>
        </footer>
      </section>
    </div>
  </main>
</template>